# ReqLab landing-page demo

The “Cómo funciona” section at `/projects#conoce-reqlab` contains a live DOM/CSS
window between the hero and “Tus proyectos”. The hero keeps “Crear proyecto”
as its primary action and offers “Ir a mis proyectos” to bypass the walkthrough.
It replaces the four static flow cards. No recording, canvas, React,
external fonts, extra runtime dependency, or model request is needed.

## Content and references

The underlying example is **SIGSAT**, the fictional thesis case documented in
`../../corpus_final_sigsat/README.md`. `demo-snapshot.ts` freezes selected outputs
already produced by ReqLab for that corpus: the 16 source filenames, their UI
type labels, the objective interpretation, RF-001 / RNF-001 / HU-001, their
citations, the original SRC-011-F001 fragment, the adaptive budget (24 suggested,
1–30 range per type), the 24 RF / 24 RNF / 24 HU result counts, and 37
observations from the saved deterministic validation report.

The document corpus has 135 fragments. Confirming the definition adds 18 user
fragments, so the confirmed view shows 153. The walkthrough starts immediately after generation with pending proposals,
then shows the actual bulk-approval dialog and its confirmation. After the
confirmation all 72 artifacts are approved, matching the saved case. Only project-name references are generalized for the landing-page audience;
requirements, evidence content and citations otherwise remain intact. Scroll
containers show excerpts.
The caption explicitly identifies the fictional case and abbreviated times.

UI references, relative to `src/app/`:

| Demo step    | UI source                                                                                                       |
| ------------ | --------------------------------------------------------------------------------------------------------------- |
| Fuentes      | `features/sources/sources-stage.component.ts`, `shared/source-library.component.ts`                             |
| Definición   | `features/definition/definition-stage.component.ts`                                                             |
| Generación   | `features/generation/generation-stage.component.ts`                                                             |
| Revisión     | `features/review/review-stage.component.ts`, `shared/evidence-panel.component.ts`                               |
| Exportación  | `features/export/export-stage.component.ts`, `src/reqlab/api/routers/exports.py` (download filename)            |
| Shared shell | `shared/topbar.component.ts`, `shared/phase-stepper.component.ts`, `shared/icon.component.ts`, `src/styles.css` |

The demo reuses the actual `IconComponent` SVG artwork and ReqLab's font stack,
colors and three-panel layout. There are no raster product assets in this UI.
No runtime database/project identifier, document storage path, or credential is
included in the snapshot. Updating the sample should preserve that boundary.

The review toolbar includes “Gestionar prioridades” and “Aprobar todo”, which
becomes the disabled “Todo aprobado” after confirmation. The simulated
confirmation uses the real UI wording, including its explanation that automatic
observations remain. Review keeps 37 observations; the real export UI counts 34
because it excludes cross-type duplicates. Approval does not erase these
findings. Export shows all 72 approved and removes the unapproved-artifact
warning, while retaining the actual draft/observation notice. The left panel's
footer matches the supplied UI reference, with the shield, full source
provenance sentence, divider, and separately spaced fragment count.

Visible chrome and the file picker use “Proyecto de ejemplo”; the caption uses
“Ejemplo ficticio”. The objective and requirement text use “El sistema”, and the
evidence heading says “comité del proyecto”. The original case name remains
only in these provenance notes and the snapshot source comment.

## Timing and rendering

| Step        | Duration | Beats (seconds within step)                                                                                             |
| ----------- | -------- | ----------------------------------------------------------------------------------------------------------------------- |
| Fuentes     | 7.5 s    | Select files 1.10; computer dialog 1.22; select all 2.40; Open 3.60; attached 3.72; process 5.00; work 5.12; ready 6.30 |
| Definición  | 5.5 s    | Press 1.20; analyze 1.32; interpretation 2.90; confirm 4.28; saved 4.40                                                 |
| Generación  | 5 s      | Press 1.30; work 1.42; complete 3.90                                                                                    |
| Revisión    | 7 s      | Citation 1.20; evidence 1.32; scroll 1.80–2.60; Approve all 3.60; dialog 3.72; confirm 5.20; approved 5.32              |
| Exportación | 5 s      | Choose Word 1.20; selected 1.32; download 3.00; progress 3.12; completed 3.75                                           |

The five steps total 30 seconds. The computer file picker and browser download
panel are simulated HTML within the stage. They never open a real OS dialog,
access local files, call the export API, or download a document. The final panel
explicitly says “Descarga de demostración” and displays
`Proyecto_de_ejemplo_requisitos.docx`, following the actual export filename convention.
The format starts on JSON so the pointer can demonstrate choosing Word; the
real export page defaults to Word. The selected format then changes the real
UI label to “Descargar DOCX”.

`demo-timeline.ts` contains the named times, pure easing, frame selection and
pointer interpolation. `MainFlowDemoComponent` adapts the skill's clock contract
to Angular. Every scene, progress value, scroll offset and pointer press derives
from that single elapsed time. Pointer targets are measured from `data-aim`
elements after layout. A press lasts 170 ms; the pointer arrives 450 ms early.
Results hold for at least one second. Scene changes fade the previous end frame
for 300 ms before drawing the next scene.

The 1200 × 750 stage uses one `ResizeObserver` scale. Its internal layout never
reflows at phone widths. A 40 ms clock discards hidden/off-screen time, clamps
delta to 250 ms, and runs only above 30% viewport intersection. All observers,
media listeners and the timer are disposed when navigating away.

Chapter buttons, pause and scrubbing are keyboard accessible. Scrubbing pauses
at an exact frame. Reduced motion displays complete end frames, hides the
pointer and retains the chapter buttons. The stage is a single labeled image
for assistive technology; the simulated controls are not interactive.

Angular defers the component until its placeholder reaches the viewport and
prefetches on idle. The prefixed `rd-` stylesheet is imported by `styles.css`,
alongside the existing global ReqLab styles. It does not change generic app
classes or keyframes. The backend and project workflow are independent of the
demo; the frozen sample is never inserted into a user's projects.

## Verification

Run `npm run build`. Browser verification requires Playwright available to Node,
an installed Microsoft Edge, and the frontend dev server:

```text
node scripts/verify-main-flow-demo.cjs http://127.0.0.1:4201 <output-directory> final
```

The browser harness intercepts the surrounding project-list API; it never
contacts a live backend. It captures 61 frames at 0.5 s intervals, compares
revisited frozen frames byte for byte, checks all twelve pointer presses and
button clipping, checks 390/340 px layouts, all five reduced-motion end frames,
the separate file-selection, attachment, processing, Word-selection and download
completion states, bulk-approval confirmation, approved artifact counts and
export state, keyboard navigation, off-screen pause, the document-hidden branch, console
errors, and absence of API mutations. The hidden-document test explicitly
overrides `document.hidden` and dispatches its change event; it is a controlled
test of that branch, not an operating-system background-tab test.

Visual QA artifacts are in the workspace's `tmp/html-demo-qa/` directory:
actual Angular reference views (fed saved fictional case data), review rounds,
phone widths, reduced-motion frames, and JSON reports. They are not app assets.
