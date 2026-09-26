import { Component, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../core/api.service';
import { Artifact } from '../core/models';
import { WorkspaceStore } from '../core/workspace.store';
import { IconComponent } from './icon.component';

@Component({
  selector: 'app-evidence-panel',
  imports: [FormsModule, IconComponent],
  template: `
    <aside class="panel results-panel">
      <div class="panel-head">
        <h2>
          {{
            store.selectedFragment()
              ? 'Evidencia de origen'
              : store.selectedArtifact()
                ? 'Detalle del artefacto'
                : 'Resultados'
          }}
        </h2>
        @if (store.selectedFragment() || store.selectedArtifact()) {
          <button
            class="icon-btn"
            type="button"
            (click)="closeDetail()"
            aria-label="Cerrar detalle"
          >
            <span aria-hidden="true">×</span>
          </button>
        } @else {
          <small>Tu espacio de salida</small>
        }
      </div>
      <div class="panel-body">
        @if (store.selectedFragment(); as fragment) {
          <div class="stage-label">
            <app-icon name="file" />
            {{
              fragment.source_code === 'USR-DEF' ? 'Aportado por el usuario' : 'Fuente documental'
            }}
          </div>
          <h3 class="detail-title">{{ fragment.heading }}</h3>
          <p class="stage-desc">{{ fragment.source_name }}</p>
          <div class="evidence-label">{{ fragment.fragment_key }}</div>
          <div class="evidence">{{ fragment.text }}</div>
          <p class="stage-desc">
            Fragmento original vinculado. El enlace permite localizar la evidencia; su pertinencia
            requiere revisión humana.
          </p>
          @if (store.selectedArtifact()) {
            <div class="gap">
              <button class="btn full" type="button" (click)="store.clearEvidence()">
                Volver al artefacto
              </button>
            </div>
          }
        } @else if (store.selectedArtifact(); as artifact) {
          <div class="row between">
            <span class="artifact-id">{{ artifact.artifact_key }}</span
            ><span class="pill outline">Versión {{ artifact.version }}</span>
          </div>
          <h3 class="detail-title">{{ artifact.title }}</h3>
          <p class="stage-desc">{{ artifact.description }}</p>
          <div class="artifact-structure">
            <p><strong>Prioridad:</strong> {{ artifact.priority }} · {{ prioritySourceLabel(artifact.priority_source) }}</p>
            @if (artifact.artifact_type !== 'HU') {
              <p><strong>Patrón:</strong> {{ artifact.ears_pattern }}</p>
              <strong>Criterios de verificación</strong>
              <ul>
                @for (criterion of artifact.verification_criteria; track criterion) {
                  <li>{{ criterion }}</li>
                } @empty {
                  <li>Pendiente de definición</li>
                }
              </ul>
            }
            @if (artifact.artifact_type === 'RNF') {
              <p><strong>Categoría:</strong> {{ artifact.quality_category || 'Pendiente' }}</p>
              <p><strong>Medición:</strong> {{ measurementLabel(artifact) }}</p>
              <p><strong>Verificación:</strong> {{ artifact.verification_method || 'Pendiente' }}</p>
            }
          </div>
          @if (artifact.validation?.warnings?.length) {
            <div class="artifact-validation">
              <strong><app-icon name="warning" /> Aspectos por revisar</strong>
              @for (warning of artifact.validation.warnings ?? []; track warning) {
                <p>{{ warning }}</p>
              }
            </div>
          } @else {
            <div class="artifact-validation ok"><strong><app-icon name="check" /> Sin alertas estructurales</strong></div>
          }
          <div class="evidence-label">RESPALDADO POR</div>
          <div class="row wrap small-gap" style="gap:6px">
            @for (citation of artifact.source_fragments; track citation) {
              <button class="citation" type="button" (click)="store.selectFragment(citation)">
                <app-icon name="link" /> {{ citation }}
              </button>
            }
          </div>
          @if (artifact.related_artifacts.length) {
            <div class="evidence-label">RELACIONADO CON</div>
            <div class="row wrap small-gap" style="gap:6px">
              @for (relation of artifact.related_artifacts; track relation) {
                <button class="relation" type="button" (click)="selectRelated(relation)">{{ relation }}</button>
              }
            </div>
          }
          <hr class="divider" />
          <label class="form-label" for="artifact-status">Decisión del analista</label>
          <select
            id="artifact-status"
            [ngModel]="artifact.status"
            (ngModelChange)="changeStatus(artifact, $event)"
            [disabled]="busy()"
          >
            <option value="propuesto">Propuesto</option>
            <option value="requiere aclaración">Requiere aclaración</option>
            <option value="aceptado">Aprobado</option>
            <option value="rechazado">Descartado</option>
          </select>
          <p class="stage-desc">La aprobación es una decisión humana.</p>
          <div class="gap">
            <button class="btn full" type="button" (click)="beginEdit(artifact)">
              <app-icon name="edit" /> Editar propuesta
            </button>
          </div>
          <div class="small-gap">
            <button class="btn full" type="button" (click)="beginAssist()">
              <app-icon name="spark" /> Ver edición asistida
            </button>
          </div>
          <hr class="divider" />
          <div class="row between">
            <h3 style="font-size:12px">Historial de cambios</h3>
            <app-icon name="history" />
          </div>
          <div class="gap">
            @for (version of versions(); track version['id']) {
              <div class="version-row">
                <strong
                  >v{{ version['version'] }} · {{ originLabel(version['change_origin']) }}</strong
                >
                <p>{{ snapshotText(version) }}</p>
              </div>
            } @empty {
              <p class="muted">Cargando historial…</p>
            }
          </div>
        } @else {
          <div class="result-grid">
            <button
              class="result-tile lilac"
              type="button"
              (click)="openReview('RF')"
              [disabled]="!ready()"
            >
              <span class="row"
                ><app-icon name="layers" /><small>{{
                  ready() ? store.counts().RF : '—'
                }}</small></span
              ><strong>Requisitos funcionales</strong>
            </button>
            <button
              class="result-tile mint"
              type="button"
              (click)="openReview('RNF')"
              [disabled]="!ready()"
            >
              <span class="row"
                ><app-icon name="shield" /><small>{{
                  ready() ? store.counts().RNF : '—'
                }}</small></span
              ><strong>Requisitos no funcionales</strong>
            </button>
            <button
              class="result-tile sand"
              type="button"
              (click)="openReview('HU')"
              [disabled]="!ready()"
            >
              <span class="row"
                ><app-icon name="chat" /><small>{{
                  ready() ? store.counts().HU : '—'
                }}</small></span
              ><strong>Historias de usuario</strong>
            </button>
            <button
              class="result-tile blue"
              type="button"
              (click)="openReview(undefined, 'trace')"
              [disabled]="!ready()"
            >
              <span class="row"
                ><app-icon name="link" /><small><app-icon name="arrow" /></small></span
              ><strong>Matriz de trazabilidad</strong>
            </button>
            <button
              class="result-tile sand"
              type="button"
              (click)="openReview(undefined, 'alerts')"
              [disabled]="!ready()"
            >
              <span class="row"
                ><app-icon name="eye" /><small>{{ alertCount() }}</small></span
              ><strong>Observaciones</strong>
            </button>
            <button
              class="result-tile lilac"
              type="button"
              (click)="openExport()"
              [disabled]="!ready()"
            >
              <span class="row"
                ><app-icon name="download" /><small><app-icon name="arrow" /></small></span
              ><strong>Exportación</strong>
            </button>
          </div>
          @if (ready()) {
            <div class="aside-section">
              <h3>Estado de la revisión</h3>
              <div class="run-line">
                <app-icon name="check" /> {{ approvedCount() }} de
                {{ store.artifacts().length }} artefactos aprobados
              </div>
              <div class="progress"><div [style.width.%]="approvalPercent()"></div></div>
              <div class="run-line">
                <app-icon name="link" /> {{ citedCount() }} artefactos con evidencia
              </div>
              <div class="run-line" style="color:var(--amber)">
                <app-icon name="warning" /> {{ alertCount() }} observaciones automáticas
              </div>
            </div>
            <div class="next-card">
              <h3><app-icon name="eye" /> Una revisión que deja huella</h3>
              <p>
                Cada cambio conserva una versión. Consulta la evidencia antes de aprobar una
                propuesta.
              </p>
              <button class="btn full" type="button" (click)="openReview()">
                Abrir revisión 
                <!-- <app-icon name="arrow" /> -->
                </button>
            </div>
          } @else {
            <div class="right-empty">
              <app-icon name="spark" />
              <p>Aquí aparecerán los artefactos<br />que construyas con tus fuentes.</p>
            </div>
            <div class="next-card">
              <h3><app-icon name="arrow" /> Tu siguiente paso</h3>
              <p>{{ nextStep() }}</p>
            </div>
          }
        }
      </div>
    </aside>

    @if (editing() && store.selectedArtifact(); as artifact) {
      <div class="modal-backdrop" (click)="editing.set(false)">
        <form class="modal-card" (click)="$event.stopPropagation()" (ngSubmit)="saveEdit(artifact)">
          <button
            class="icon-btn modal-close"
            type="button"
            (click)="editing.set(false)"
            aria-label="Cerrar"
          >
            ×
          </button>
          <h2>Editar {{ artifact.artifact_key }}</h2>
          <p>El cambio creará una versión y devolverá el artefacto al estado Propuesto. Si cambias su tipo, ReqLab asignará un identificador coherente y actualizará las relaciones existentes.</p>
          <label class="form-label gap" for="edit-type">Tipo de artefacto</label>
          <select id="edit-type" name="artifactType" [(ngModel)]="draft.artifact_type">
            <option value="RF">Requisito funcional (RF)</option>
            <option value="RNF">Requisito no funcional (RNF)</option>
            <option value="HU">Historia de usuario (HU)</option>
          </select>
          <label class="form-label gap" for="edit-title">Título</label
          ><input id="edit-title" name="title" [(ngModel)]="draft.title" />
          <label class="form-label gap" for="edit-text">Redacción del artefacto</label
          ><textarea
            id="edit-text"
            name="description"
            style="min-height:140px"
            [(ngModel)]="draft.description"
          ></textarea>
          <label class="form-label gap" for="edit-priority">Prioridad</label>
          <select id="edit-priority" name="priority" [(ngModel)]="draft.priority">
            <option value="No definida">No definida</option>
            <option value="Alta">Alta</option>
            <option value="Media">Media</option>
            <option value="Baja">Baja</option>
          </select>
          @if (draft.artifact_type !== 'HU') {
            <label class="form-label gap" for="edit-ears">Patrón EARS</label>
            <select id="edit-ears" name="earsPattern" [(ngModel)]="draft.ears_pattern">
              <option value="No determinado">No determinado</option>
              <option value="Ubicuo">Ubicuo</option>
              <option value="Basado en evento">Basado en evento</option>
              <option value="Basado en estado">Basado en estado</option>
              <option value="Comportamiento no deseado">Comportamiento no deseado</option>
              <option value="Característica opcional">Característica opcional</option>
              <option value="Complejo">Complejo</option>
              <option value="No aplica">No aplica</option>
            </select>
            <label class="form-label gap" for="edit-verification">Criterios de verificación (uno por línea)</label>
            <textarea id="edit-verification" name="verification" [(ngModel)]="draft.verification_criteria"></textarea>
          }
          @if (draft.artifact_type === 'RNF') {
            <label class="form-label gap" for="edit-quality">Categoría de calidad</label>
            <input id="edit-quality" name="qualityCategory" [(ngModel)]="draft.quality_category" />
            <div class="row gap">
              <div style="flex:1"><label class="form-label" for="edit-metric">Métrica</label><input id="edit-metric" name="metric" [(ngModel)]="draft.metric" /></div>
              <div style="flex:1"><label class="form-label" for="edit-unit">Unidad</label><input id="edit-unit" name="unit" [(ngModel)]="draft.unit" /></div>
            </div>
            <label class="form-label gap" for="edit-target">Umbral o valor objetivo</label>
            <input id="edit-target" name="target" [(ngModel)]="draft.target" />
            <label class="form-label gap" for="edit-method">Método de verificación</label>
            <textarea id="edit-method" name="verificationMethod" [(ngModel)]="draft.verification_method"></textarea>
          }
          @if (draft.artifact_type === 'HU') {
            <label class="form-label gap" for="edit-acceptance">Criterios de aceptación (uno por línea)</label>
            <textarea id="edit-acceptance" name="acceptance" [(ngModel)]="draft.acceptance_criteria"></textarea>
          }
          <label class="form-label gap" for="edit-rationale">Justificación sustentada (opcional)</label>
          <textarea id="edit-rationale" name="rationale" [(ngModel)]="draft.rationale"></textarea>
          <div class="actions">
            <button class="btn" type="button" (click)="editing.set(false)">Descartar cambio</button
            ><button class="btn primary" type="submit" [disabled]="busy()">
              Guardar nueva versión
            </button>
          </div>
        </form>
      </div>
    }

    @if (assisting() && store.selectedArtifact(); as artifact) {
      <div class="modal-backdrop" (click)="closeAssist()">
        <div class="modal-card" (click)="$event.stopPropagation()">
          <button
            class="icon-btn modal-close"
            type="button"
            (click)="closeAssist()"
            aria-label="Cerrar"
          >
            ×
          </button>
          <h2>Propuesta de edición asistida</h2>
          <p>
            Indica el cambio deseado. El agente utilizará el corpus del proyecto y tú decidirás si
            se incorpora.
          </p>
          @if (!store.proposal()) {
            <label class="form-label gap" for="assist-instruction">Qué deseas mejorar</label
            ><textarea
              id="assist-instruction"
              [(ngModel)]="instruction"
              placeholder="Ej. Haz el enunciado verificable sin añadir información nueva."
            ></textarea>
            <div class="actions">
              <button class="btn" type="button" (click)="closeAssist()">Cancelar</button
              ><button
                class="btn primary"
                type="button"
                (click)="propose(artifact)"
                [disabled]="busy() || instruction.trim().length < 3"
              >
                Preparar propuesta
              </button>
            </div>
          } @else if (store.proposal(); as proposal) {
            <label class="form-label gap">Versión actual</label>
            <div class="quote-mini">{{ artifact.description }}</div>
            <label class="form-label gap">Redacción sugerida</label>
            <div class="quote-mini">{{ proposal.proposal.description }}</div>
            <div class="actions">
              <button class="btn" type="button" (click)="decide(false)">Descartar cambio</button
              ><button class="btn primary" type="button" (click)="decide(true)" [disabled]="busy()">
                Aceptar propuesta
              </button>
            </div>
          }
        </div>
      </div>
    }
  `,
})
export class EvidencePanelComponent {
  readonly store = inject(WorkspaceStore);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly versions = signal<Array<Record<string, unknown>>>([]);
  readonly editing = signal(false);
  readonly assisting = signal(false);
  readonly busy = signal(false);
  instruction = '';
  draft: {
    artifact_type: Artifact['artifact_type']; title: string; description: string;
    priority: Artifact['priority']; ears_pattern: Artifact['ears_pattern'];
    verification_criteria: string; acceptance_criteria: string; quality_category: string;
    metric: string; unit: string; target: string; verification_method: string; rationale: string;
  } = {
    artifact_type: 'RF',
    title: '',
    description: '',
    priority: 'No definida',
    ears_pattern: 'No determinado',
    verification_criteria: '',
    acceptance_criteria: '',
    quality_category: '',
    metric: '',
    unit: '',
    target: '',
    verification_method: '',
    rationale: '',
  };

  constructor() {
    effect(() => {
      const artifact = this.store.selectedArtifact();
      this.versions.set([]);
      if (artifact) void this.loadVersions(artifact);
    });
  }
  ready(): boolean {
    return this.store.artifacts().length > 0 && Boolean(this.store.project()?.definition_confirmed);
  }
  approvedCount(): number {
    return this.store.artifacts().filter((item) => item.status === 'aceptado').length;
  }
  citedCount(): number {
    return this.store.artifacts().filter((item) => item.source_fragments.length > 0).length;
  }
  approvalPercent(): number {
    return this.store.artifacts().length
      ? (this.approvedCount() / this.store.artifacts().length) * 100
      : 0;
  }
  alertCount(): number {
    const report = this.store.validation();
    return (
      (report?.artifacts_without_citations.length ?? 0) +
      Object.values(report?.invalid_citations ?? {}).reduce((sum, items) => sum + items.length, 0) +
      (report?.possible_duplicates.length ?? 0) +
      (report?.cross_type_duplicates?.length ?? 0) +
      Object.values(report?.invalid_relations ?? {}).reduce((sum, items) => sum + items.length, 0) +
      (report?.user_stories_with_invalid_format?.length ?? 0) +
      (report?.user_stories_without_acceptance_criteria?.length ?? 0) +
      (report?.taxonomy_warnings.length ?? 0) +
      (report?.requirements_without_verification_criteria?.length ?? 0) +
      (report?.requirements_with_invalid_ears?.length ?? 0) +
      (report?.non_functional_measurement_pending?.length ?? 0) +
      (report?.undefined_priorities?.length ?? 0) +
      (report?.priorities_without_source?.length ?? 0)
    );
  }
  nextStep(): string {
    const project = this.store.project();
    if (!project?.source_count) return 'Añade fuentes para dar contexto a tu proyecto.';
    if (!project.definition_confirmed)
      return 'Confirma la definición antes de iniciar la generación.';
    return 'Inicia la generación para obtener propuestas trazables.';
  }
  openReview(type?: string, tab: 'artifacts' | 'trace' | 'alerts' | 'run' = 'artifacts'): void {
    const project = this.store.project();
    if (project)
      void this.router.navigate(['/projects', project.id, 'review'], {
        queryParams: { tab, ...(type ? { type } : {}) },
      });
  }
  openExport(): void {
    const project = this.store.project();
    if (project) void this.router.navigate(['/projects', project.id, 'export']);
  }
  closeDetail(): void {
    if (this.store.selectedFragment() && this.store.selectedArtifact()) this.store.clearEvidence();
    else this.store.clearDetail();
  }
  selectRelated(artifactKey: string): void {
    const artifact = this.store.artifacts().find((item) => item.artifact_key === artifactKey);
    if (artifact) this.store.selectArtifact(artifact);
  }
  beginEdit(artifact: Artifact): void {
    this.draft = {
      artifact_type: artifact.artifact_type,
      title: artifact.title,
      description: artifact.description,
      priority: artifact.priority,
      ears_pattern: artifact.ears_pattern,
      verification_criteria: artifact.verification_criteria.join('\n'),
      acceptance_criteria: artifact.acceptance_criteria.join('\n'),
      quality_category: artifact.quality_category,
      metric: artifact.metric,
      unit: artifact.unit,
      target: artifact.target,
      verification_method: artifact.verification_method,
      rationale: artifact.rationale,
    };
    this.editing.set(true);
  }
  async loadVersions(artifact: Artifact): Promise<void> {
    const project = this.store.project();
    if (!project) return;
    try {
      this.versions.set(await firstValueFrom(this.api.listVersions(project.id, artifact.id)));
    } catch {
      this.versions.set([]);
    }
  }
  snapshotText(version: Record<string, unknown>): string {
    const snapshot = version['snapshot'] as Record<string, unknown> | undefined;
    return String(snapshot?.['description'] ?? '');
  }
  originLabel(origin: unknown): string {
    return (
      (
        {
          generation: 'Propuesta inicial',
          manual_revision: 'Edición manual',
          manual_reclassification: 'Reclasificación manual',
          reference_rekey: 'Relación actualizada',
          bulk_approval: 'Aprobación masiva',
          ai_revision: 'Edición asistida',
        } as Record<string, string>
      )[String(origin)] ?? String(origin ?? 'Cambio')
    );
  }
  async changeStatus(artifact: Artifact, status: Artifact['status']): Promise<void> {
    await this.update({ ...artifact, status });
  }
  async saveEdit(artifact: Artifact): Promise<void> {
    await this.update({
      ...artifact,
      artifact_type: this.draft.artifact_type,
      title: this.draft.title.trim(),
      description: this.draft.description.trim(),
      priority: this.draft.priority,
      ears_pattern: this.draft.artifact_type === 'HU' ? 'No aplica' : this.draft.ears_pattern,
      verification_criteria: this.lines(this.draft.verification_criteria),
      acceptance_criteria: this.lines(this.draft.acceptance_criteria),
      quality_category: this.draft.artifact_type === 'RNF' ? this.draft.quality_category.trim() : '',
      metric: this.draft.artifact_type === 'RNF' ? this.draft.metric.trim() : '',
      unit: this.draft.artifact_type === 'RNF' ? this.draft.unit.trim() : '',
      target: this.draft.artifact_type === 'RNF' ? this.draft.target.trim() : '',
      verification_method: this.draft.artifact_type === 'RNF' ? this.draft.verification_method.trim() : '',
      rationale: this.draft.rationale.trim(),
      status: 'propuesto',
    });
    this.editing.set(false);
  }
  private async update(artifact: Artifact): Promise<void> {
    const project = this.store.project();
    if (!project) return;
    this.busy.set(true);
    try {
      const updated = await firstValueFrom(this.api.updateArtifact(project.id, artifact));
      await this.store.refreshProject();
      this.store.selectArtifact(updated);
    } catch (error) {
      this.store.setError(this.store.message(error));
    } finally {
      this.busy.set(false);
    }
  }
  private lines(value: string): string[] {
    return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  }
  prioritySourceLabel(value: Artifact['priority_source']): string {
    return ({ corpus: 'según el corpus', usuario: 'decidida por el usuario', legado: 'sin procedencia histórica', no_definida: 'pendiente' })[value];
  }
  measurementLabel(artifact: Artifact): string {
    const parts = [artifact.metric, artifact.target, artifact.unit].filter(Boolean);
    return parts.length ? parts.join(' · ') : 'Pendiente de definición';
  }
  beginAssist(): void {
    this.instruction = '';
    this.store.proposal.set(null);
    this.assisting.set(true);
  }
  closeAssist(): void {
    this.assisting.set(false);
    this.store.proposal.set(null);
  }
  async propose(artifact: Artifact): Promise<void> {
    const project = this.store.project();
    if (!project) return;
    this.busy.set(true);
    try {
      this.store.proposal.set(
        await firstValueFrom(this.api.proposeRevision(project.id, artifact.id, this.instruction)),
      );
    } catch (error) {
      this.store.setError(this.store.message(error));
    } finally {
      this.busy.set(false);
    }
  }
  async decide(accept: boolean): Promise<void> {
    const project = this.store.project();
    const proposal = this.store.proposal();
    if (!project || !proposal) return;
    this.busy.set(true);
    try {
      await firstValueFrom(this.api.decideRevision(project.id, proposal.id, accept));
      this.closeAssist();
      await this.store.refreshProject();
    } catch (error) {
      this.store.setError(this.store.message(error));
    } finally {
      this.busy.set(false);
    }
  }
}
