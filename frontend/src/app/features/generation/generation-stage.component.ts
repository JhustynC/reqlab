import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../../core/api.service';
import {
  ArtifactType,
  GenerationBudgetItem,
  GenerationLimits,
  GenerationRecommendations,
} from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-generation-stage',
  imports: [IconComponent],
  template: `
    <div class="stage-body generation-stage">
      <div class="stage-label"><app-icon name="spark" /> De las fuentes a las propuestas</div>
      <h2>{{ busy() ? 'Construyendo tus artefactos…' : generationComplete() ? 'La generación está completa' : generationFailed() ? 'La generación quedó incompleta' : 'Todo listo para generar' }}</h2>
      <p class="stage-desc">{{ busy() ? 'Puedes seguir cada etapa del proceso mientras los agentes consultan el corpus del proyecto.' : generationFailed() ? 'Los agentes terminados quedaron guardados. Puedes continuar desde el primer paso pendiente sin repetirlos.' : 'El sistema prepara propuestas de RF, RNF e historias de usuario y comprueba sus referencias. Tú decides qué conservar.' }}</p>

      @if (!busy() && !store.artifacts().length && !generationFailed()) {
        <section class="generation-budget" aria-labelledby="generation-budget-title">
          <header class="generation-budget-head">
            <div>
              <span class="eyebrow">Presupuesto adaptativo</span>
              <h3 id="generation-budget-title">Define el máximo por tipo de artefacto</h3>
            </div>
            @if (recommendations()) {
              <span class="pill outline">{{ recommendations()?.inputs?.fragment_count }} fragmentos analizados</span>
            }
          </header>
          <p class="generation-budget-note">
            Es un tope, no una cuota: cada agente puede devolver menos elementos si la evidencia no sustenta más.
          </p>

          @if (loadingRecommendations()) {
            <div class="budget-loading"><span class="spinner small"></span> Calculando rangos desde el corpus…</div>
          } @else {
            @if (recommendationError()) {
              <div class="alert">
                {{ recommendationError() }}
                <button class="btn secondary small" type="button" (click)="retryRecommendations()">Reintentar</button>
              </div>
            } @else {
              <div class="budget-grid">
                @for (item of budgetTypes; track item.type) {
                  <article class="budget-card">
                    <div class="row between">
                      <div>
                        <span class="artifact-id">{{ item.type }}</span>
                        <strong>{{ item.label }}</strong>
                      </div>
                      <div class="budget-value"><small>Hasta</small><b>{{ selectedLimit(item.type) }}</b></div>
                    </div>
                    <input
                      type="range"
                      [min]="recommendationFor(item.type).minimum"
                      [max]="recommendationFor(item.type).maximum"
                      [value]="selectedLimit(item.type)"
                      [attr.aria-label]="'Máximo de ' + item.label"
                      (input)="setLimit(item.type, $event)"
                    />
                    <div class="budget-scale">
                      <span>Mín. {{ recommendationFor(item.type).minimum }}</span>
                      <span>Sugerido {{ recommendationFor(item.type).suggested }}</span>
                      <span>Máx. {{ recommendationFor(item.type).maximum }}</span>
                    </div>
                    <small class="budget-evidence">
                      {{ recommendationFor(item.type).signal_fragments }} fragmentos contienen indicios de {{ item.shortLabel }}.
                    </small>
                  </article>
                }
              </div>
              <small class="budget-method">
                Método {{ recommendations()?.method_version }} · La selección y el cálculo quedarán registrados en la ejecución.
              </small>
            }
          }
        </section>
      }

      @if (!busy() && store.run()?.parameters?.metrics; as metrics) {
        <section class="generation-summary" [class.partial]="generationFailed()" aria-labelledby="generation-summary-title">
          <header class="generation-budget-head">
            <div>
              <span class="eyebrow">{{ generationFailed() ? 'Avance recuperable' : 'Resultado de la ejecución' }}</span>
              <h3 id="generation-summary-title">{{ generatedTotal() }} artefactos generados de un máximo de {{ requestedTotal() }}</h3>
            </div>
            <span class="pill" [class.green]="generationComplete()" [class.amber]="generationFailed()">{{ generationComplete() ? 'Completa' : 'Incompleta' }}</span>
          </header>
          <div class="generation-summary-grid">
            @for (item of budgetTypes; track item.type) {
              <div>
                <span class="artifact-id">{{ item.type }}</span>
                <strong>{{ generatedCount(item.type) }} / {{ requestedCount(item.type) }}</strong>
                <small>{{ item.label }} · generado / máximo solicitado</small>
              </div>
            }
          </div>
          <p class="generation-budget-note">Los máximos no son cuotas. Una cantidad menor es válida cuando el agente no encuentra evidencia suficiente. En una ejecución incompleta solo se reanuda el primer agente pendiente.</p>
        </section>
      }

      <div class="row between gap"><small class="muted">{{ busy() ? (store.run()?.parameters?.message || 'Ejecución en curso') : store.artifacts().length ? '6 etapas completadas' : (store.sources().length + ' fuentes · definición confirmada') }}</small><span class="pill" [class.purple]="busy()" [class.green]="!busy()">{{ progress() }} %</span></div>
      <div class="progress" role="progressbar" aria-label="Progreso de generación" aria-valuemin="0" aria-valuemax="100" [attr.aria-valuenow]="progress()"><div [style.width.%]="progress()"></div></div>
      <div class="execution">
        @for (step of steps; track step.key) {
          <div class="execution-step" [class.done]="stepDone(step.order)" [class.active]="store.run()?.parameters?.step === step.key && busy()">
            <span class="status-icon">@if (stepDone(step.order)) { <app-icon name="check" /> } @else { {{ step.order }} }</span>
            <div class="grow"><strong>{{ stepLabel(step) }}</strong><small>{{ step.description }}</small></div>
            @if (store.run()?.parameters?.step === step.key && busy()) { <span class="pill green">En curso</span> } @else if (stepDone(step.order)) { <small class="muted">Listo</small> } @else { <app-icon [name]="step.icon" /> }
          </div>
        }
      </div>
      @if (store.run()?.status === 'failed') { <div class="alert error"><strong>La ejecución se detuvo.</strong> {{ store.run()?.error_message || 'La generación no pudo completarse.' }} @if (completedTypes().length) { <span>Se conservaron: {{ completedTypes().join(', ') }}.</span> }</div> }
      <footer class="stage-footer">
        <small>Las propuestas siempre pasan por revisión humana.</small>
        @if (generationComplete() && !busy()) { <button class="btn primary" type="button" (click)="openReview()">Revisar propuestas <app-icon name="arrow" /></button> }
        @else if (generationFailed() && !busy()) { <button class="btn primary" type="button" (click)="resume()"><app-icon name="arrow" /> Reanudar desde {{ nextPendingStep() }}</button> }
        @else { <button class="btn primary" type="button" (click)="start()" [disabled]="busy() || loadingRecommendations() || !!recommendationError() || !recommendations() || !store.project()?.definition_confirmed">@if (busy()) { <span class="spinner small"></span> Generando } @else { <app-icon name="spark" /> Generar propuestas }</button> }
      </footer>
    </div>
  `,
})
export class GenerationStageComponent implements OnInit, OnDestroy {
  readonly store = inject(WorkspaceStore);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly busy = signal(false);
  readonly loadingRecommendations = signal(false);
  readonly recommendationError = signal('');
  readonly recommendations = signal<GenerationRecommendations | null>(null);
  readonly limits = signal<GenerationLimits>({ RF: 12, RNF: 12, HU: 12 });
  readonly generationComplete = computed(() => this.store.run()?.status === 'completed');
  readonly generationFailed = computed(() => this.store.run()?.status === 'failed');
  readonly completedTypes = computed(() => this.store.run()?.parameters.metrics?.completed_types ?? []);
  private timer?: ReturnType<typeof setTimeout>;
  readonly budgetTypes: Array<{ type: ArtifactType; label: string; shortLabel: string }> = [
    { type: 'RF', label: 'Requisitos funcionales', shortLabel: 'funcionalidad' },
    { type: 'RNF', label: 'Requisitos no funcionales', shortLabel: 'calidad o restricción' },
    { type: 'HU', label: 'Historias de usuario', shortLabel: 'actor y valor' },
  ];
  readonly steps = [
    { key: 'retrieval', label: 'Recuperación de evidencia', description: 'Seleccionar contexto relevante para cada tipo de artefacto', icon: 'search', order: 1 },
    { key: 'generating_rf', label: 'Requisitos funcionales', description: 'Proponer capacidades observables del sistema', icon: 'layers', order: 2 },
    { key: 'generating_rnf', label: 'Requisitos no funcionales', description: 'Proponer atributos y restricciones verificables', icon: 'shield', order: 3 },
    { key: 'generating_hu', label: 'Historias de usuario', description: 'Relacionar rol, objetivo y beneficio', icon: 'chat', order: 4 },
    { key: 'validation', label: 'Trazabilidad', description: 'Vincular cada propuesta con sus fragmentos fuente', icon: 'link', order: 5 },
    { key: 'completed', label: 'Consistencia', description: 'Identificar aspectos que requieren revisión humana', icon: 'eye', order: 6 },
  ];

  ngOnInit(): void {
    const activeRun = this.store.run();
    if (activeRun?.status === 'running') {
      this.busy.set(true);
      void this.poll(activeRun.id);
    }
    void this.loadRecommendations();
  }

  retryRecommendations(): void {
    void this.loadRecommendations();
  }

  private async loadRecommendations(): Promise<void> {
    const project = this.store.project();
    if (!project?.definition_confirmed || this.store.artifacts().length) return;
    this.loadingRecommendations.set(true);
    this.recommendationError.set('');
    try {
      const result = await firstValueFrom(this.api.generationRecommendations(project.id));
      this.recommendations.set(result);
      this.limits.set({
        RF: result.limits.RF.suggested,
        RNF: result.limits.RNF.suggested,
        HU: result.limits.HU.suggested,
      });
    } catch {
      this.recommendationError.set('No se pudo calcular el rango adaptativo. Puedes continuar con los límites conservadores de respaldo.');
    } finally {
      this.loadingRecommendations.set(false);
    }
  }

  recommendationFor(type: ArtifactType): GenerationBudgetItem {
    return this.recommendations()?.limits[type] ?? {
      minimum: 1,
      suggested: 12,
      maximum: 20,
      signal_fragments: 0,
      signal_ratio: 0,
    };
  }

  selectedLimit(type: ArtifactType): number {
    return this.limits()[type];
  }

  setLimit(type: ArtifactType, event: Event): void {
    const recommendation = this.recommendationFor(type);
    const raw = Number((event.target as HTMLInputElement).value) || recommendation.suggested;
    const value = Math.max(recommendation.minimum, Math.min(recommendation.maximum, raw));
    this.limits.update((current) => ({ ...current, [type]: value }));
  }

  progress(): number { return this.store.run()?.parameters.progress ?? (this.generationComplete() ? 100 : 0); }
  generatedCount(type: ArtifactType): number { return this.store.run()?.parameters.metrics?.generated_counts?.[type] ?? this.store.counts()[type]; }
  requestedCount(type: ArtifactType): number { return this.store.run()?.parameters.metrics?.generation_limits?.[type] ?? this.store.run()?.parameters.generation_limits?.[type] ?? 0; }
  generatedTotal(): number { return this.budgetTypes.reduce((total, item) => total + this.generatedCount(item.type), 0); }
  requestedTotal(): number { return this.budgetTypes.reduce((total, item) => total + this.requestedCount(item.type), 0); }
  nextPendingStep(): string { return this.budgetTypes.find((item) => !this.completedTypes().includes(item.type))?.type ?? 'validación'; }
  openReview(): void { const project = this.store.project(); if (project) void this.router.navigate(['/projects', project.id, 'review']); }
  async start(): Promise<void> {
    const project = this.store.project(); if (!project) return;
    this.busy.set(true); this.store.clearError();
    try {
      const queued = await firstValueFrom(this.api.startGeneration(project.id, this.limits()));
      await this.poll(queued.run_id);
    } catch (error) { this.store.setError(this.store.message(error)); this.busy.set(false); }
  }
  async resume(): Promise<void> {
    const project = this.store.project();
    const run = this.store.run();
    if (!project || !run || run.status !== 'failed') return;
    this.busy.set(true); this.store.clearError();
    try {
      const queued = await firstValueFrom(this.api.resumeGeneration(project.id, run.id));
      await this.poll(queued.run_id);
    } catch (error) { this.store.setError(this.store.message(error)); this.busy.set(false); }
  }
  private async poll(runId: string): Promise<void> {
    try {
      const run = await firstValueFrom(this.api.getRun(runId));
      this.store.run.set(run);
      if (run.status === 'completed') {
        this.busy.set(false); await this.store.refreshProject();
        return;
      }
      if (run.status === 'failed') { this.busy.set(false); return; }
      this.timer = setTimeout(() => void this.poll(runId), 1200);
    } catch (error) { this.store.setError(this.store.message(error)); this.busy.set(false); }
  }
  stepDone(order: number): boolean {
    if (this.generationComplete()) return true;
    const stepType: Partial<Record<number, ArtifactType>> = { 2: 'RF', 3: 'RNF', 4: 'HU' };
    if (stepType[order] && this.completedTypes().includes(stepType[order]!)) return true;
    const current = this.steps.find((item) => item.key === this.store.run()?.parameters.step)?.order ?? 0;
    return order < current || this.store.run()?.status === 'completed';
  }
  stepLabel(step: { key: string; label: string }): string {
    const type =
      step.key === 'generating_rf'
        ? 'RF'
        : step.key === 'generating_rnf'
          ? 'RNF'
          : step.key === 'generating_hu'
            ? 'HU'
            : null;
    return type && this.store.artifacts().length > 0
      ? `${step.label} (${this.store.counts()[type]})`
      : step.label;
  }
  ngOnDestroy(): void { if (this.timer) clearTimeout(this.timer); }
}
