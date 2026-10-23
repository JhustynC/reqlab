// Requires Playwright, a local `npm start`, and an installed Edge browser.
// Usage: node scripts/verify-main-flow-demo.cjs <base URL> <output directory> [round]
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');

const base = process.argv[2] || 'http://127.0.0.1:4201';
const output = path.resolve(process.argv[3] || 'tmp/html-demo-qa');
const round = process.argv[4] || 'final';

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1100 },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    const errors = [];
    const mutations = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (event) => {
      if (event.type() === 'error') errors.push(event.text());
    });
    page.on('request', (request) => {
      if (request.url().includes('/api/') && request.method() !== 'GET')
        mutations.push(request.url());
    });
    // The surrounding projects list is independent of the demo. Never use a live backend in QA.
    await page.route('**/api/**', (route) => route.fulfill({ json: [] }));
    await page.goto(`${base}/projects`);
    await page.locator('#conoce-reqlab').scrollIntoViewIfNeeded();
    await page.locator('.rd-stage').waitFor();
    await page.locator('.rd-demo').scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    const seek = async (seconds) => {
      await page.locator('.rd-scrubber').evaluate((element, value) => {
        element.value = value;
        element.dispatchEvent(new Event('input', { bubbles: true }));
      }, seconds);
      await page.evaluate(
        () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
      );
    };
    const currentTime = () => page.locator('.rd-scrubber').inputValue().then(Number);
    // 0.5 s coverage throughout every scene, including crossfades and both working/result states.
    for (let at = 0; at <= 30; at += 0.5) {
      await seek(at);
      await page
        .locator('.rd-demo')
        .screenshot({ path: path.join(output, `${round}-${at.toFixed(1).padStart(4, '0')}.png`) });
    }
    // Revisit frames in reverse order: an exact frame must not depend on its preceding state.
    for (const at of [29.2, 24.7, 23, 20.2, 17.8, 12.8, 6.8, 2.8, 1.15]) {
      await seek(at);
      const first = await page.locator('.rd-stage').screenshot();
      await seek(15.5);
      await seek(at);
      const second = await page.locator('.rd-stage').screenshot();
      assert.equal(
        crypto.createHash('sha256').update(first).digest('hex'),
        crypto.createHash('sha256').update(second).digest('hex'),
        `Frame at ${at} changed after seeking`,
      );
    }
    // All twelve presses must land inside their measured target, and targets must fit inside the panel.
    for (const [at, aim] of [
      [1.15, 'choose-files'],
      [2.45, 'computer-files'],
      [3.65, 'open-files'],
      [5.05, 'process'],
      [8.75, 'analyze'],
      [11.83, 'confirm'],
      [14.35, 'generate'],
      [19.25, 'citation'],
      [21.65, 'approve-all'],
      [23.25, 'confirm-approval'],
      [26.25, 'word'],
      [28.05, 'download'],
    ]) {
      await seek(at);
      const geometry = await page.locator('.rd-stage').evaluate((stage, aim) => {
        const target = stage.querySelector(`[data-aim="${aim}"]`).getBoundingClientRect();
        const pointer = stage.querySelector('.rd-pointer').getBoundingClientRect();
        const panel = stage.querySelector('.rd-main').getBoundingClientRect();
        return {
          x: pointer.left,
          y: pointer.top,
          target: {
            left: target.left,
            right: target.right,
            top: target.top,
            bottom: target.bottom,
          },
          panelBottom: panel.bottom,
          press: stage.querySelector('.rd-pointer').classList.contains('rd-pointer-press'),
        };
      }, aim);
      assert(geometry.press, `Missing press at ${at}`);
      assert(
        geometry.x >= geometry.target.left &&
          geometry.x <= geometry.target.right &&
          geometry.y >= geometry.target.top &&
          geometry.y <= geometry.target.bottom,
        `Pointer missed ${aim}`,
      );
      assert(geometry.target.bottom <= geometry.panelBottom - 8, `Clipped target: ${aim}`);
    }
    for (const [step, at, result] of [
      [0, 7, '16 fuentes disponibles'],
      [1, 12.7, 'Definición confirmada.'],
      [2, 17.8, 'La generación está completa'],
      [3, 24.7, 'Todo aprobado'],
      [4, 29.5, 'Completada'],
    ]) {
      await seek(at);
      assert.equal(await page.locator('.rd-stage').getAttribute('data-step'), String(step));
      assert((await page.locator('.rd-stage').innerText()).includes(result));
    }
    await seek(0.9);
    assert.equal(await page.locator('.rd-file-row').count(), 0, 'Files appeared before selection');
    await seek(1.7);
    assert(
      await page
        .locator('.rd-picker-overlay')
        .evaluate((e) => getComputedStyle(e).visibility === 'visible'),
    );
    assert.equal(await page.locator('.rd-picker-file-selected').count(), 0);
    await seek(2.8);
    assert.equal(await page.locator('.rd-picker-file-selected').count(), 16);
    await seek(4.1);
    assert.equal(await page.locator('.rd-file-row').count(), 16);
    assert(
      await page
        .locator('.rd-picker-overlay')
        .evaluate((e) => getComputedStyle(e).visibility === 'hidden'),
    );
    await seek(25.9);
    assert((await page.locator('.rd-format-selected').innerText()).includes('JSON'));
    await seek(26.6);
    assert((await page.locator('.rd-format-selected').innerText()).includes('Documento Word'));
    await seek(28.4);
    assert((await page.locator('.rd-download-popover').innerText()).includes('Descargando…'));
    await seek(29.2);
    assert(
      (await page.locator('.rd-download-popover').innerText()).includes(
        'Proyecto_de_ejemplo_requisitos.docx',
      ),
    );
    assert((await page.locator('.rd-download-popover').innerText()).includes('Completada'));
    await seek(20);
    assert.equal(await page.locator('.rd-review-actions').count(), 1);
    assert((await page.locator('.rd-review-count').innerText()).includes('72 por revisar'));
    await seek(22.4);
    assert(
      await page
        .locator('.rd-approval-overlay')
        .evaluate((e) => getComputedStyle(e).visibility === 'visible'),
    );
    assert(
      (await page.locator('.rd-approval-dialog').innerText()).includes(
        'Las observaciones automáticas no desaparecerán.',
      ),
    );
    await seek(24);
    assert((await page.locator('[data-aim="approve-all"]').innerText()).includes('Todo aprobado'));
    assert((await page.locator('.rd-review-count').innerText()).includes('0 por revisar'));
    assert(
      (await page.locator('.rd-review-state').innerText()).includes(
        '72 de 72 artefactos aprobados',
      ),
    );
    assert.equal(await page.locator('.rd-artifact-head .rd-green').count(), 3);
    assert(
      await page
        .locator('.rd-approval-overlay')
        .evaluate((e) => getComputedStyle(e).visibility === 'hidden'),
    );
    assert(
      (await page.locator('.rd-library-foot').innerText()).includes(
        'Fuentes listas para consultar. Cada fragmento conserva su procedencia.',
      ),
    );
    await seek(29.2);
    assert(
      (await page.locator('.rd-export-summary').innerText()).includes(
        '72 artefactos · 72 aprobados',
      ),
    );
    assert(!(await page.locator('.rd-body').innerText()).includes('sin aprobación'));
    assert(
      (await page.locator('.rd-body').innerText()).includes(
        '34 observaciones automáticas pendientes',
      ),
    );
    // The demo now appears immediately below the hero. A shorter viewport is
    // needed to move it fully off screen while scrolling back to the top.
    await page.setViewportSize({ width: 1440, height: 600 });
    // Off-screen/hidden time is discarded, and returning does not fast-forward.
    await seek(4.9);
    await page.getByRole('button', { name: 'Reproducir demostración' }).click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(180);
    const offscreen = await currentTime();
    await page.waitForTimeout(650);
    assert.equal(await currentTime(), offscreen, 'Clock advanced off screen');
    await page.locator('.rd-demo').scrollIntoViewIfNeeded();
    await page.waitForTimeout(200);
    assert((await currentTime()) - offscreen < 0.4, 'Returned window fast-forwarded');
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.waitForTimeout(100); // Let the last visible signal update reach the DOM.
    const hidden = await currentTime();
    await page.waitForTimeout(650);
    assert.equal(await currentTime(), hidden, 'Clock advanced while document.hidden');
    await page.evaluate(() => {
      delete document.hidden;
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.waitForTimeout(200);
    assert((await currentTime()) - hidden < 0.4, 'Restored document fast-forwarded');
    await page.setViewportSize({ width: 1440, height: 1100 });
    // Fixed stage, one scale, no document overflow at phone widths.
    for (const width of [390, 340]) {
      await page.setViewportSize({ width, height: 900 });
      await page.locator('.rd-demo').scrollIntoViewIfNeeded();
      await seek(29.2);
      const geometry = await page.locator('.rd-stage').evaluate((element) => ({
        width: element.getBoundingClientRect().width,
        height: element.getBoundingClientRect().height,
        scroll: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
      }));
      assert(Math.abs(geometry.width / geometry.height - 1.6) < 0.001);
      assert(geometry.scroll <= geometry.viewport, `Horizontal overflow at ${width}`);
      await page
        .locator('.rd-demo')
        .screenshot({ path: path.join(output, `${round}-phone-${width}.png`) });
    }
    // A dynamic preference change must also show complete frames, with usable real chapter buttons.
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const [index, name] of [
      'Fuentes',
      'Definición',
      'Generación',
      'Revisión',
      'Exportación',
    ].entries()) {
      await page
        .getByRole('navigation', { name: 'Pasos de la demostración' })
        .getByRole('button', { name: new RegExp(name) })
        .click();
      await page.waitForFunction(
        (index) => document.querySelector('.rd-stage').dataset.step === String(index),
        index,
      );
      assert.equal(await page.locator('.rd-stage').getAttribute('data-step'), String(index));
      assert.equal(
        await page.locator('.rd-stage').getAttribute('data-time'),
        String([7.5, 5.5, 5, 7, 5][index]),
      );
      assert.equal(
        await page.locator('.rd-scene').evaluate((element) => getComputedStyle(element).opacity),
        '1',
      );
      assert.equal(
        await page.locator('.rd-pointer').evaluate((element) => getComputedStyle(element).opacity),
        '0',
      );
      await page
        .locator('.rd-demo')
        .screenshot({ path: path.join(output, `${round}-reduced-${index}.png`) });
    }
    const active = page.locator('.rd-steps button[aria-current="step"]');
    await active.focus();
    await page.keyboard.press('Shift+Tab');
    assert((await page.evaluate(() => document.activeElement.textContent)).includes('Revisión'));
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('.rd-stage').dataset.step === '3');
    assert.equal(await page.locator('.rd-stage').getAttribute('data-step'), '3');
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page
      .locator('.rd-steps button')
      .evaluateAll((elements) => elements.forEach((element) => element.blur()));
    await seek(29.2);
    await page.locator('.rd-demo').screenshot({ path: path.join(output, `${round}-cover.png`) });
    assert.deepEqual(mutations, [], 'Demo issued a mutating API request');
    assert.deepEqual(errors, [], 'Browser errors');
    const report = {
      round,
      frames: 61,
      deterministicFrames: 9,
      measuredClicks: 12,
      phoneWidths: [390, 340],
      reducedMotionSteps: 5,
      offscreen: 'passed',
      documentHidden: 'passed',
      keyboard: 'passed',
      mutations,
      errors,
    };
    await fs.writeFile(path.join(output, `${round}-report.json`), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
