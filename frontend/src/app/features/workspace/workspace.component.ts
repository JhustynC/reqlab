import { Component, DestroyRef, ElementRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { Phase } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { EvidencePanelComponent } from '../../shared/evidence-panel.component';
import { PhaseStepperComponent } from '../../shared/phase-stepper.component';
import { SourceLibraryComponent } from '../../shared/source-library.component';
import { TopbarComponent } from '../../shared/topbar.component';
import { DefinitionStageComponent } from '../definition/definition-stage.component';
import { ExportStageComponent } from '../export/export-stage.component';
import { GenerationStageComponent } from '../generation/generation-stage.component';
import { ReviewStageComponent } from '../review/review-stage.component';
import { SourcesStageComponent } from '../sources/sources-stage.component';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-workspace',
  imports: [
    TopbarComponent, PhaseStepperComponent, SourceLibraryComponent, EvidencePanelComponent,
    SourcesStageComponent, DefinitionStageComponent, GenerationStageComponent,
    ReviewStageComponent, ExportStageComponent, IconComponent,
  ],
  template: `
    <app-topbar [projectName]="store.project()?.name ?? ''" [projectId]="store.project()?.id ?? ''" [exportEnabled]="(store.project()?.artifact_count ?? 0) > 0" />
    @if (store.project(); as project) {
      <app-phase-stepper [project]="project" [phase]="phase()" />
      @if (store.error()) { <div class="alert error workspace-alert">{{ store.error() }} <button (click)="store.clearError()">Cerrar</button></div> }
         <main class="workspace" [class.sources-collapsed]="sourcesCollapsed()" [class.results-collapsed]="resultsCollapsed()" [style.--sources-width.px]="sourceWidth()" [style.--results-width.px]="resultsWidth()">
        <app-source-library />
        <button class="panel-restore source-restore" type="button" (click)="restorePanel('sources')" aria-label="Restaurar ancho de fuentes"><app-icon name="arrow" /></button>
        <div class="resize-handle source-resize" role="separator" aria-label="Cambiar ancho de fuentes" (pointerdown)="startResize('sources', $event)"></div>
        <section class="panel main-panel" aria-live="polite">
          <div class="panel-head"><h2>{{ panelTitle() }}</h2><small>{{ phase() === 'review' ? 'Propuestas y decisiones' : 'Paso ' + (phaseIndex() + 1) + ' de 5' }}</small></div>
          @switch (phase()) {
            @case ('sources') { <app-sources-stage /> }
            @case ('definition') { <app-definition-stage /> }
            @case ('generation') { <app-generation-stage /> }
            @case ('review') { <app-review-stage /> }
            @case ('export') { <app-export-stage /> }
          }
        </section>
        <app-evidence-panel />
        <button class="panel-restore results-restore" type="button" (click)="restorePanel('results')" aria-label="Restaurar ancho de resultados"><app-icon name="back" /></button>
        <div class="resize-handle results-resize" role="separator" aria-label="Cambiar ancho de resultados" (pointerdown)="startResize('results', $event)"></div>
      </main>
    } @else if (store.loading()) {
      <div class="page-loading"><span class="spinner"></span><p>Cargando el proyecto…</p></div>
    } @else {
      <div class="page-loading"><p>No se pudo abrir el proyecto.</p><button class="btn primary" (click)="goHome()">Volver a proyectos</button></div>
    }
  `,
})
export class WorkspaceComponent {
  readonly store = inject(WorkspaceStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly phase = signal<Phase>('sources');
  readonly sourceWidth = signal<number | null>(null);
  readonly resultsWidth = signal<number | null>(null);
  readonly sourceRestoreWidth = signal<number | null>(null);
  readonly resultsRestoreWidth = signal<number | null>(null);
  readonly sourcesCollapsed = signal(false);
  readonly resultsCollapsed = signal(false);
  private readonly host = inject(ElementRef<HTMLElement>);
  private resizing: 'sources' | 'results' | null = null;
  private resizeMoved = false;
  private resizeStartX = 0;
  private resizeStartWidth = 0;
  private readonly phases: Phase[] = ['sources', 'definition', 'generation', 'review', 'export'];

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const projectId = params.get('id');
      const routePhase = params.get('phase') as Phase;
      if (projectId) {
        this.phase.set(this.phases.includes(routePhase) ? routePhase : 'sources');
        this.store.clearDetail();
        void this.store.loadWorkspace(projectId);
      }
    });
  }
  goHome(): void { void this.router.navigate(['/projects']); }
  phaseIndex(): number { return this.phases.indexOf(this.phase()); }
  panelTitle(): string { return ['Preparación de fuentes', 'Definición del proyecto', 'Generación de artefactos', 'Espacio de revisión', 'Entrega del proyecto'][this.phaseIndex()]; }
  startResize(panel: 'sources' | 'results', event: PointerEvent): void {
    if (window.innerWidth <= 980) return;
    event.preventDefault();
    const host = this.host.nativeElement as HTMLElement;
    const workspace = host.querySelector<HTMLElement>('.workspace');
    const element = host.querySelector<HTMLElement>(panel === 'sources' ? '.sources-panel' : '.results-panel');
    if (!workspace || !element) return;
    this.resizing = panel;
    this.resizeMoved = false;
    this.resizeStartX = event.clientX;
    this.resizeStartWidth = element.getBoundingClientRect().width;
    if (panel === 'sources') this.sourceRestoreWidth.set(this.resizeStartWidth);
    else this.resultsRestoreWidth.set(this.resizeStartWidth);
    document.body.classList.add('is-resizing-panel');
    document.addEventListener('pointermove', this.resizePanel);
    document.addEventListener('pointerup', this.stopResize, { once: true });
  }
  restorePanel(panel: 'sources' | 'results'): void {
    if (panel === 'sources') {
      this.sourceWidth.set(this.sourceRestoreWidth() ?? this.sourceWidth());
      this.sourcesCollapsed.set(false);
    } else {
      this.resultsWidth.set(this.resultsRestoreWidth() ?? this.resultsWidth());
      this.resultsCollapsed.set(false);
    }
  }
  private readonly resizePanel = (event: PointerEvent): void => {
    if (!this.resizing) return;
    const delta = event.clientX - this.resizeStartX;
    if (!this.resizeMoved && Math.abs(delta) < 4) return;
    this.resizeMoved = true;
    const host = this.host.nativeElement as HTMLElement;
    const workspace = host.querySelector<HTMLElement>('.workspace');
    if (!workspace) return;
    const sourceElement = host.querySelector<HTMLElement>('.sources-panel');
    const resultsElement = host.querySelector<HTMLElement>('.results-panel');
    if (!sourceElement || !resultsElement) return;
    const sourceWidth = this.sourceWidth() ?? sourceElement.getBoundingClientRect().width;
    const resultsWidth = this.resultsWidth() ?? resultsElement.getBoundingClientRect().width;
    const availableWidth = workspace.getBoundingClientRect().width;
    const minimumCenterWidth = 420;
    const gapWidth = 24;
    const minimumExpandedWidth = 215;
    if (this.resizing === 'sources') {
      const requestedWidth = this.resizeStartWidth + delta;
      if (requestedWidth < minimumExpandedWidth) {
        this.sourceWidth.set(42);
        this.sourcesCollapsed.set(true);
      } else {
        const width = this.clamp(requestedWidth, minimumExpandedWidth, availableWidth - resultsWidth - gapWidth - minimumCenterWidth);
        this.sourceWidth.set(width);
        this.sourceRestoreWidth.set(width);
        this.sourcesCollapsed.set(false);
      }
    } else {
      const requestedWidth = this.resizeStartWidth - delta;
      if (requestedWidth < minimumExpandedWidth) {
        this.resultsWidth.set(42);
        this.resultsCollapsed.set(true);
      } else {
        const width = this.clamp(requestedWidth, minimumExpandedWidth, availableWidth - sourceWidth - gapWidth - minimumCenterWidth);
        this.resultsWidth.set(width);
        this.resultsRestoreWidth.set(width);
        this.resultsCollapsed.set(false);
      }
    }
  };
  private readonly stopResize = (): void => {
    this.resizing = null;
    document.body.classList.remove('is-resizing-panel');
    document.removeEventListener('pointermove', this.resizePanel);
  };
  private clamp(value: number, minimum: number, maximum: number): number { return Math.min(Math.max(value, minimum), Math.max(minimum, maximum)); }
}
