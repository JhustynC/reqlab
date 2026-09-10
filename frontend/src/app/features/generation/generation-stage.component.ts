import { Component, OnDestroy, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { WorkspaceStore } from '../../core/workspace.store';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-generation-stage',
  imports: [IconComponent],
  template: `
    <div class="stage-body generation-stage">
      <div class="stage-label"><app-icon name="spark" /> De las fuentes a las propuestas</div>
      <h2>{{ busy() ? 'Construyendo tus artefactos…' : store.artifacts().length ? 'La generación está completa' : 'Todo listo para generar' }}</h2>
      <p class="stage-desc">{{ busy() ? 'Puedes seguir cada etapa del proceso mientras los agentes consultan el corpus del proyecto.' : 'El sistema prepara propuestas de RF, RNF e historias de usuario y comprueba sus referencias. Tú decides qué conservar.' }}</p>
      <div class="row between gap"><small class="muted">{{ busy() ? (store.run()?.parameters?.message || 'Ejecución en curso') : store.artifacts().length ? '6 etapas completadas' : (store.sources().length + ' fuentes · definición confirmada') }}</small><span class="pill" [class.purple]="busy()" [class.green]="!busy()">{{ progress() }} %</span></div>
      <div class="progress" role="progressbar" aria-label="Progreso de generación" aria-valuemin="0" aria-valuemax="100" [attr.aria-valuenow]="progress()"><div [style.width.%]="progress()"></div></div>
      <div class="execution">
        @for (step of steps; track step.key) {
          <div class="execution-step" [class.done]="stepDone(step.order)" [class.active]="store.run()?.parameters?.step === step.key && busy()">
            <span class="status-icon">@if (stepDone(step.order)) { <app-icon name="check" /> } @else { {{ step.order }} }</span>
            <div class="grow"><strong>{{ step.label }}</strong><small>{{ step.description }}</small></div>
            @if (store.run()?.parameters?.step === step.key && busy()) { <span class="pill green">En curso</span> } @else if (stepDone(step.order)) { <small class="muted">Listo</small> } @else { <app-icon [name]="step.icon" /> }
          </div>
        }
      </div>
      @if (store.run()?.status === 'failed') { <div class="alert error">{{ store.run()?.error_message || 'La generación no pudo completarse.' }}</div> }
      <footer class="stage-footer">
        <small>Las propuestas siempre pasan por revisión humana.</small>
        @if (store.artifacts().length && !busy()) { <button class="btn primary" type="button" (click)="openReview()">Revisar propuestas <app-icon name="arrow" /></button> }
        @else { <button class="btn primary" type="button" (click)="start()" [disabled]="busy() || !store.project()?.definition_confirmed">@if (busy()) { <span class="spinner small"></span> Generando } @else { <app-icon name="spark" /> Generar propuestas }</button> }
      </footer>
    </div>
  `,
})
export class GenerationStageComponent implements OnDestroy {
  readonly store = inject(WorkspaceStore);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly busy = signal(false);
  readonly limit = signal(1);
  private timer?: ReturnType<typeof setTimeout>;
  readonly steps = [
    { key: 'retrieval', label: 'Recuperación de evidencia', description: 'Seleccionar contexto relevante para cada tipo de artefacto', icon: 'search', order: 1 },
    { key: 'generating_rf', label: 'Requisitos funcionales', description: 'Proponer capacidades observables del sistema', icon: 'layers', order: 2 },
    { key: 'generating_rnf', label: 'Requisitos no funcionales', description: 'Proponer atributos y restricciones verificables', icon: 'shield', order: 3 },
    { key: 'generating_hu', label: 'Historias de usuario', description: 'Relacionar rol, objetivo y beneficio', icon: 'chat', order: 4 },
    { key: 'validation', label: 'Trazabilidad', description: 'Vincular cada propuesta con sus fragmentos fuente', icon: 'link', order: 5 },
    { key: 'completed', label: 'Consistencia', description: 'Identificar aspectos que requieren revisión humana', icon: 'eye', order: 6 },
  ];
  setLimit(event: Event): void { this.limit.set(Math.max(3, Math.min(20, Number((event.target as HTMLInputElement).value) || 12))); }
  progress(): number { return this.store.run()?.parameters.progress ?? (this.store.artifacts().length ? 100 : 0); }
  openReview(): void { const project = this.store.project(); if (project) void this.router.navigate(['/projects', project.id, 'review']); }
  async start(): Promise<void> {
    const project = this.store.project(); if (!project) return;
    this.busy.set(true); this.store.clearError();
    try {
      const queued = await firstValueFrom(this.api.startGeneration(project.id, this.limit()));
      await this.poll(queued.run_id);
    } catch (error) { this.store.setError(this.store.message(error)); this.busy.set(false); }
  }
  private async poll(runId: string): Promise<void> {
    try {
      const run = await firstValueFrom(this.api.getRun(runId));
      this.store.run.set(run);
      if (run.status === 'completed') {
        this.busy.set(false); await this.store.refreshProject();
        const project = this.store.project(); if (project) await this.router.navigate(['/projects', project.id, 'review']);
        return;
      }
      if (run.status === 'failed') { this.busy.set(false); return; }
      this.timer = setTimeout(() => void this.poll(runId), 1200);
    } catch (error) { this.store.setError(this.store.message(error)); this.busy.set(false); }
  }
  stepDone(order: number): boolean {
    if (!this.busy() && this.store.artifacts().length > 0) return true;
    const current = this.steps.find((item) => item.key === this.store.run()?.parameters.step)?.order ?? 0;
    return order < current || this.store.run()?.status === 'completed';
  }
  ngOnDestroy(): void { if (this.timer) clearTimeout(this.timer); }
}
