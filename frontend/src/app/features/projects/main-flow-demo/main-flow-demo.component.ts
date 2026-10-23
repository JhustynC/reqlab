import {
  AfterViewInit,
  Component,
  ElementRef,
  NgZone,
  OnDestroy,
  afterEveryRender,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { IconComponent } from '../../../shared/icon.component';
import { DEMO_SNAPSHOT } from './demo-snapshot';
import {
  DEFINITION,
  DEMO_STEPS,
  EXPORT,
  GENERATION,
  Point,
  REVIEW,
  SOURCE,
  TOTAL,
  ease,
  frameAt,
  glide,
} from './demo-timeline';

@Component({
  selector: 'app-main-flow-demo',
  imports: [IconComponent],
  templateUrl: './main-flow-demo.component.html',
})
export class MainFlowDemoComponent implements AfterViewInit, OnDestroy {
  readonly data = DEMO_SNAPSHOT;
  readonly steps = DEMO_STEPS;
  readonly total = TOTAL;
  readonly source = SOURCE;
  readonly definition = DEFINITION;
  readonly generation = GENERATION;
  readonly review = REVIEW;
  readonly export = EXPORT;
  readonly sourceFilenames = DEMO_SNAPSHOT.sources
    .map((source) => source.original_name)
    .join('" "');
  readonly budgetTypes = ['RF', 'RNF', 'HU'] as const;
  readonly resultTiles = [
    { label: 'Requisitos funcionales', icon: 'layers', type: 'RF', tone: 'lilac' },
    { label: 'Requisitos no funcionales', icon: 'shield', type: 'RNF', tone: 'mint' },
    { label: 'Historias de usuario', icon: 'chat', type: 'HU', tone: 'sand' },
    { label: 'Matriz de trazabilidad', icon: 'link', type: null, tone: 'blue' },
    { label: 'Observaciones', icon: 'eye', type: null, tone: 'sand' },
    { label: 'Exportación', icon: 'download', type: null, tone: 'lilac' },
  ] as const;
  readonly elapsed = signal(0);
  readonly paused = signal(false);
  readonly still = signal(false);
  readonly scale = signal(1);
  private readonly targets = signal<Record<string, Point>>({});
  private readonly zone = inject(NgZone);
  private readonly viewport = viewChild.required<ElementRef<HTMLElement>>('viewport');
  private readonly stage = viewChild.required<ElementRef<HTMLElement>>('stage');
  private visible = false;
  private last = 0;
  private timer?: ReturnType<typeof setInterval>;
  private resize?: ResizeObserver;
  private intersection?: IntersectionObserver;
  private media?: MediaQueryList;

  readonly position = computed(() => frameAt(this.elapsed()));
  // Hold the preceding end frame for its 300 ms fade-out before drawing the new scene.
  readonly scene = computed(() => {
    const { i, t } = this.position();
    if (this.still()) return { i, t: this.steps[i].dur, opacity: 1 };
    if (i > 0 && t < 0.3)
      return { i: i - 1, t: this.steps[i - 1].dur, opacity: 1 - ease(t, 0, 0.3) };
    return { i, t, opacity: ease(t, i > 0 ? 0.3 : 0, i > 0 ? 0.75 : 0.45) };
  });
  readonly t = computed(() => this.scene().t);
  readonly sourceReady = computed(() => this.scene().i > 0 || this.t() >= SOURCE.done);
  readonly sourceWorking = computed(() => this.t() >= SOURCE.work && this.t() < SOURCE.done);
  readonly pickerOpen = computed(
    () => this.scene().i === 0 && this.t() >= SOURCE.picker && this.t() < SOURCE.attached,
  );
  readonly filesAttached = computed(() => this.scene().i > 0 || this.t() >= SOURCE.attached);
  readonly wordSelected = computed(() => this.t() >= EXPORT.selected);
  readonly downloadStarted = computed(() => this.scene().i === 4 && this.t() >= EXPORT.work);
  readonly downloadComplete = computed(() => this.scene().i === 4 && this.t() >= EXPORT.done);
  readonly analysisReady = computed(() => this.t() >= DEFINITION.done);
  readonly confirmed = computed(
    () => this.scene().i > 1 || (this.scene().i === 1 && this.t() >= DEFINITION.saved),
  );
  readonly generationWorking = computed(
    () => this.t() >= GENERATION.work && this.t() < GENERATION.done,
  );
  readonly generated = computed(
    () => this.scene().i > 2 || (this.scene().i === 2 && this.t() >= GENERATION.done),
  );
  readonly progress = computed(() =>
    Math.round(ease(this.t(), GENERATION.work, GENERATION.done) * 100),
  );
  readonly approved = computed(
    () => this.scene().i > 3 || (this.scene().i === 3 && this.t() >= REVIEW.saved),
  );
  readonly approvalOpen = computed(
    () => this.scene().i === 3 && this.t() >= REVIEW.dialog && this.t() < REVIEW.saved,
  );
  readonly evidenceOpen = computed(
    () => this.scene().i === 3 && this.t() >= REVIEW.open && this.t() < REVIEW.saved,
  );
  readonly execution = [
    {
      label: 'Recuperación de evidencia',
      description: 'Seleccionar contexto relevante para cada tipo de artefacto',
      icon: 'search',
    },
    {
      label: 'Requisitos funcionales',
      description: 'Proponer capacidades observables del sistema',
      icon: 'layers',
    },
    {
      label: 'Requisitos no funcionales',
      description: 'Proponer atributos y restricciones verificables',
      icon: 'shield',
    },
    {
      label: 'Historias de usuario',
      description: 'Relacionar rol, objetivo y beneficio',
      icon: 'chat',
    },
    {
      label: 'Trazabilidad',
      description: 'Vincular cada propuesta con sus fragmentos fuente',
      icon: 'link',
    },
    {
      label: 'Consistencia',
      description: 'Identificar aspectos que requieren revisión humana',
      icon: 'eye',
    },
  ];
  readonly panelTitle = computed(
    () =>
      [
        'Contexto y fuentes',
        'Definición del proyecto',
        'Generación de artefactos',
        'Espacio de revisión',
        'Entrega del proyecto',
      ][this.scene().i],
  );
  readonly pointer = computed(() => {
    const { i, t } = this.scene();
    const aims = this.targets();
    const hidden = { x: 0, y: 0, press: false, opacity: 0 };
    if (this.still()) return hidden;
    const rest = { x: 1090, y: 650 };
    if (i === 0) {
      if (t >= SOURCE.done) return hidden;
      const point = (key: string) => aims[key] ?? rest;
      return {
        ...glide(
          t,
          [
            { from: 0.15, to: SOURCE.choose - 0.45, point: point('choose-files') },
            { from: 1.25, to: SOURCE.select - 0.45, point: point('computer-files') },
            { from: 2.55, to: SOURCE.open - 0.45, point: point('open-files') },
            { from: 3.8, to: SOURCE.click - 0.45, point: point('process') },
            { from: 5.4, to: 6.15, point: rest },
          ],
          [SOURCE.choose, SOURCE.select, SOURCE.open, SOURCE.click],
        ),
        opacity: 1 - ease(t, 6.15, 6.3),
      };
    }
    if (i === 4) {
      return {
        ...glide(
          t,
          [
            { from: 0.2, to: EXPORT.select - 0.45, point: aims['word'] ?? rest },
            { from: 1.6, to: EXPORT.click - 0.45, point: aims['download'] ?? rest },
            { from: 3.4, to: 4.15, point: rest },
          ],
          [EXPORT.select, EXPORT.click],
        ),
        opacity: 1 - ease(t, 4.15, 4.5),
      };
    }
    if (i === 3) {
      return {
        ...glide(
          t,
          [
            { from: 0.2, to: REVIEW.click - 0.45, point: aims['citation'] ?? rest },
            { from: 1.65, to: 2.35, point: rest },
            { from: 2.5, to: REVIEW.approve - 0.45, point: aims['approve-all'] ?? rest },
            { from: 3.9, to: REVIEW.confirm - 0.45, point: aims['confirm-approval'] ?? rest },
            { from: 5.55, to: 6.3, point: rest },
          ],
          [REVIEW.click, REVIEW.approve, REVIEW.confirm],
        ),
        opacity: 1 - ease(t, 6.3, 6.6),
      };
    }
    const aim =
      aims[
        i === 0
          ? 'process'
          : i === 1 && t < DEFINITION.done
            ? 'analyze'
            : i === 1
              ? 'confirm'
              : i === 2
                ? 'generate'
                : 'citation'
      ];
    if (!aim || this.still()) return { x: 0, y: 0, press: false, opacity: 0 };
    let clicks: number[], moves;
    if (i === 1) {
      clicks = [DEFINITION.click, DEFINITION.confirm];
      const analyze = aims['analyze'] ?? rest;
      // The initial target disappears once its result has appeared.
      moves =
        t < DEFINITION.done
          ? [
              { from: 0.15, to: 0.75, point: analyze },
              { from: 1.55, to: 2.25, point: rest },
            ]
          : [
              { from: 0, to: 0.01, point: rest },
              { from: 3.1, to: DEFINITION.confirm - 0.45, point: aim },
              { from: 4.68, to: 5.23, point: rest },
            ];
    } else {
      const click = i === 2 ? GENERATION.click : REVIEW.click;
      clicks = [click];
      moves = [
        { from: 0.2, to: click - 0.45, point: aim },
        { from: click + 0.4, to: click + 1.15, point: rest },
      ];
    }
    const fadeAt = i === 1 ? 5.23 : 3;
    return { ...glide(t, moves, clicks), opacity: 1 - ease(t, fadeAt, fadeAt + 0.4) };
  });

  constructor() {
    afterEveryRender(() => this.measureTargets());
  }

  ngAfterViewInit(): void {
    const element = this.viewport().nativeElement;
    this.media = window.matchMedia('(prefers-reduced-motion: reduce)');
    this.onMotionChange();
    this.media.addEventListener('change', this.onMotionChange);
    document.addEventListener('visibilitychange', this.onVisibilityChange);
    this.resize = new ResizeObserver(([entry]) => this.scale.set(entry.contentRect.width / 1200));
    this.resize.observe(element);
    this.intersection = new IntersectionObserver(
      ([entry]) => {
        this.visible = entry.isIntersecting && entry.intersectionRatio >= 0.3;
        this.last = performance.now();
      },
      { threshold: [0, 0.3] },
    );
    this.intersection.observe(element);
    this.last = performance.now();
    this.zone.runOutsideAngular(() => {
      this.timer = setInterval(() => {
        const now = performance.now();
        const dt = Math.min(0.25, (now - this.last) / 1000);
        this.last = now;
        if (!this.visible || document.hidden || this.paused() || this.still()) return;
        this.elapsed.update((value) => (value + dt) % TOTAL);
      }, 40);
    });
  }

  playStep(index: number): void {
    const start = this.steps.slice(0, index).reduce((sum, step) => sum + step.dur, 0);
    this.elapsed.set(start + (this.still() ? this.steps[index].dur - 0.001 : 0));
    this.paused.set(false);
    this.last = performance.now();
  }

  seek(event: Event): void {
    this.elapsed.set(Number((event.target as HTMLInputElement).value));
    this.paused.set(true);
  }

  togglePlayback(): void {
    this.paused.update((value) => !value);
    this.last = performance.now();
  }

  timeLabel(seconds: number): string {
    return `0:${Math.floor(seconds).toString().padStart(2, '0')}`;
  }

  private readonly onMotionChange = (): void => {
    this.still.set(this.media?.matches ?? false);
  };
  private readonly onVisibilityChange = (): void => {
    this.last = performance.now();
  };

  private measureTargets(): void {
    const stage = this.stage()?.nativeElement;
    if (!stage) return;
    const bounds = stage.getBoundingClientRect();
    const k = bounds.width / 1200;
    if (!k) return;
    const targets: Record<string, Point> = {};
    stage.querySelectorAll<HTMLElement>('[data-aim]').forEach((element) => {
      const box = element.getBoundingClientRect();
      targets[element.dataset['aim']!] = {
        x: Math.round(((box.left - bounds.left + box.width * 0.55) / k) * 100) / 100,
        y: Math.round(((box.top - bounds.top + box.height * 0.6) / k) * 100) / 100,
      };
    });
    if (JSON.stringify(targets) !== JSON.stringify(this.targets())) this.targets.set(targets);
  }

  ngOnDestroy(): void {
    clearInterval(this.timer);
    this.resize?.disconnect();
    this.intersection?.disconnect();
    this.media?.removeEventListener('change', this.onMotionChange);
    document.removeEventListener('visibilitychange', this.onVisibilityChange);
  }
}
