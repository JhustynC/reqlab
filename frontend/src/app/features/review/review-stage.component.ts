import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { Artifact } from '../../core/models';
import { ApiService } from '../../core/api.service';
import { WorkspaceStore } from '../../core/workspace.store';
import { IconComponent } from '../../shared/icon.component';

type ReviewTab = 'artifacts' | 'trace' | 'alerts' | 'run';
type ArtifactFilter = 'Todos' | 'RF' | 'RNF' | 'HU' | 'Aprobados';

@Component({
  selector: 'app-review-stage',
  imports: [IconComponent],
  template: `
    <div class="stage-body review-stage">
      <div class="stage-label"><app-icon name="spark" /> El criterio final es tuyo</div>
      <h2>De propuestas a requisitos</h2>
      <p class="stage-desc">
        Inspecciona la evidencia, ajusta la redacción y registra tus decisiones antes de preparar la
        entrega.
      </p>
      <div class="tabs" aria-label="Vistas de revisión">
        <button
          type="button"
          [class.active]="tab() === 'artifacts'"
          (click)="openView('artifacts')"
        >
          Artefactos</button
        ><button type="button" [class.active]="tab() === 'trace'" (click)="openView('trace')">
          Trazabilidad</button
        ><button type="button" [class.active]="tab() === 'alerts'" (click)="openView('alerts')">
          Observaciones ({{ alertCount() }})</button
        ><button type="button" [class.active]="tab() === 'run'" (click)="openView('run')">
          Ejecución
        </button>
      </div>

      @if (tab() === 'artifacts') {
        <div class="row between wrap" style="margin-bottom:15px;gap:10px">
          <div>
            <small class="muted"
              >{{ store.artifacts().length }} propuestas · {{ pendingCount() }} por revisar</small
            ><br />
          </div>
            <small style="font-size:10px;color:var(--mint);display:flex;align-items:center;gap:3px;margin-top:10px"
              ><app-icon name="link" /> {{ citedCount() }} con fuente vinculada</small
            >
          <button
            class="btn primary"
            type="button"
            (click)="approvalWarningOpen.set(true)"
            [disabled]="busy() || remainingApprovalCount() === 0"
          >
            <app-icon name="check" />
            {{ remainingApprovalCount() === 0 ? 'Todo aprobado' : 'Aprobar todo' }}
          </button>
        </div>
        <div class="filter-row">
          @for (item of filters; track item) {
            <button
              type="button"
              [class.active]="filter() === item"
              (click)="filter.set(item)"
              [attr.aria-pressed]="filter() === item"
            >
              {{ filterLabel(item) }}
            </button>
          }
        </div>
        @for (artifact of filtered(); track artifact.id) {
          <article class="artifact" [class.selected]="store.selectedArtifact()?.id === artifact.id">
            <div class="artifact-header">
              <div class="row">
                <span class="artifact-id">{{ artifact.artifact_key }}</span
                ><small class="muted" style="font-size:10px"
                  >Prioridad {{ artifact.priority.toLowerCase() }}</small
                >
              </div>
              <span
                class="pill"
                [class.green]="artifact.status === 'aceptado'"
                [class.red]="artifact.status === 'rechazado'"
                [class.purple]="artifact.status !== 'aceptado' && artifact.status !== 'rechazado'"
                >{{ statusLabel(artifact.status) }}</span
              >
            </div>
            <h3>{{ artifact.title }}</h3>
            <p>{{ artifact.description }}</p>
            @if (artifact.validation?.status === 'requiere_revision') {
              <div class="artifact-warning">
                <app-icon name="warning" /> Requiere revisión automática
              </div>
            }
            @if (artifact.acceptance_criteria.length) {
              <ul class="criteria">
                @for (criterion of artifact.acceptance_criteria; track criterion) {
                  <li>{{ criterion }}</li>
                }
              </ul>
            }
            @if (artifact.related_artifacts.length) {
              <div class="relation-row">
                <small>Relacionado con</small>
                @for (relation of artifact.related_artifacts; track relation) {
                  <button type="button" class="relation" (click)="selectRelated(relation)">
                    {{ relation }}
                  </button>
                }
              </div>
            }
            <div class="artifact-bottom">
              <div class="row wrap" style="gap:5px">
                @for (citation of artifact.source_fragments; track citation) {
                  <button
                    class="citation"
                    type="button"
                    (click)="inspectCitation(artifact, citation)"
                  >
                    <app-icon name="link" /> {{ citation }}
                  </button>
                }
              </div>
              <button class="btn text" type="button" (click)="store.selectArtifact(artifact)">
                Revisar <app-icon name="arrow" />
              </button>
            </div>
          </article>
        } @empty {
          <p class="empty-filter">Todavía no hay artefactos en esta selección.</p>
        }
      } @else if (tab() === 'trace') {
        <div class="notice">
          <app-icon name="link" />
          <div>
            <strong
              >{{ citedCount() }} de {{ store.artifacts().length }} artefactos con
              referencias</strong
            ><br />Abre cualquier cita para leer el fragmento original.
          </div>
        </div>
        <div class="table-wrap gap">
          <table>
            <thead>
              <tr>
                <th>Artefacto</th>
                <th>Origen documental</th>
                <th>Relaciones</th>
                <th>Revisión</th>
              </tr>
            </thead>
            <tbody>
              @for (artifact of store.artifacts(); track artifact.id) {
                <tr>
                  <td>
                    <button
                      class="artifact-id"
                      type="button"
                      (click)="store.selectArtifact(artifact)"
                    >
                      {{ artifact.artifact_key }}</button
                    ><br />{{ artifact.title }}
                  </td>
                  <td>
                    <div class="row wrap" style="gap:6px">
                      @for (citation of artifact.source_fragments; track citation) {
                        <button
                          class="citation"
                          type="button"
                          (click)="inspectCitation(artifact, citation)"
                        >
                          <app-icon name="link" /> {{ citation }}
                        </button>
                      }
                    </div>
                  </td>
                  <td>
                    @for (relation of artifact.related_artifacts; track relation) {
                      <button type="button" class="relation" (click)="selectRelated(relation)">
                        {{ relation }}
                      </button>
                    } @empty {
                      <span class="muted">—</span>
                    }
                  </td>
                  <td>{{ statusLabel(artifact.status) }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else if (tab() === 'alerts') {
        <div class="row between">
          <small class="muted">{{ alertCount() }} observaciones automáticas</small
          ><span class="pill amber">Revisión humana</span>
        </div>
        @if (alertCount()) {
          <div class="notice amber gap observation-guide">
            <app-icon name="warning" />
            <div>
              <strong>Las observaciones no modifican artefactos automáticamente.</strong><br />Abre
              el elemento indicado para editar su redacción o tipo, revisar su evidencia y registrar
              tu decisión.
            </div>
          </div>
        }
        @if (!alertCount()) {
          <div class="notice gap">
            <app-icon name="check" />
            <div>
              <strong>Sin alertas estructurales</strong><br />La ausencia de alertas no sustituye la
              evaluación semántica por expertos.
            </div>
          </div>
        }
        @if ((store.validation()?.artifacts_without_citations?.length ?? 0) > 0) {
          <article class="alert-card">
            <span class="pill amber">Trazabilidad</span>
            <h3>Artefactos sin evidencia vinculada</h3>
            <div class="observation-actions">
              @for (
                artifactKey of store.validation()?.artifacts_without_citations ?? [];
                track artifactKey
              ) {
                <button class="btn text" type="button" (click)="reviewArtifact(artifactKey)">
                  Revisar {{ artifactKey }} <app-icon name="arrow" />
                </button>
              }
            </div>
          </article>
        }
        @if (invalidCitationEntries().length) {
          <article class="alert-card">
            <span class="pill amber">Referencia inválida</span>
            <h3>Citas que no existen en el corpus</h3>
            @for (item of invalidCitationEntries(); track item.artifactKey) {
              <div class="observation-item">
                <p>
                  <strong>{{ item.artifactKey }}</strong> · {{ item.values.join(', ') }}
                </p>
                <button class="btn text" type="button" (click)="reviewArtifact(item.artifactKey)">
                  Revisar <app-icon name="arrow" />
                </button>
              </div>
            }
          </article>
        }
        @if ((store.validation()?.possible_duplicates?.length ?? 0) > 0) {
          <article class="alert-card">
            <span class="pill amber">Posible duplicado</span>
            <h3>Artefactos con similitud léxica</h3>
            <p>
              @for (
                item of store.validation()?.possible_duplicates ?? [];
                track item.left + item.right
              ) {
                <span class="observation-item"
                  ><span
                    >{{ item.left }} / {{ item.right }} ·
                    {{ (item.jaccard * 100).toFixed(0) }}%</span
                  ><span
                    ><button class="btn text" type="button" (click)="reviewArtifact(item.left)">
                      {{ item.left }}</button
                    ><button class="btn text" type="button" (click)="reviewArtifact(item.right)">
                      {{ item.right }}
                    </button></span
                  ></span
                >
              }
            </p>
          </article>
        }
        @if ((store.validation()?.taxonomy_warnings?.length ?? 0) > 0) {
          <article class="alert-card">
            <span class="pill amber">Clasificación</span>
            <h3>Elementos que requieren revisar su tipo</h3>
            <p>
              @for (item of store.validation()?.taxonomy_warnings ?? []; track item.artifact_id) {
                <span class="observation-item"
                  ><span>{{ item.artifact_id }} · {{ item.reason }}</span
                  ><button
                    class="btn text"
                    type="button"
                    (click)="reviewArtifact(item.artifact_id)"
                  >
                    Revisar y reclasificar <app-icon name="arrow" /></button
                ></span>
              }
            </p>
          </article>
        }
        @if ((store.validation()?.cross_type_duplicates?.length ?? 0) > 0) {
          <article class="alert-card">
            <span class="pill amber">Relación entre tipos</span>
            <h3>Posible solapamiento entre RF, RNF o HU</h3>
            <p>
              @for (
                item of store.validation()?.cross_type_duplicates ?? [];
                track item.left + item.right
              ) {
                <span class="observation-item"
                  ><span
                    >{{ item.left }} / {{ item.right }} ·
                    {{ (item.jaccard * 100).toFixed(0) }}%</span
                  ><span
                    ><button class="btn text" type="button" (click)="reviewArtifact(item.left)">
                      {{ item.left }}</button
                    ><button class="btn text" type="button" (click)="reviewArtifact(item.right)">
                      {{ item.right }}
                    </button></span
                  ></span
                >
              }
            </p>
          </article>
        }
        @if (invalidRelationEntries().length) {
          <article class="alert-card">
            <span class="pill amber">Relación inválida</span>
            <h3>Vínculos con artefactos inexistentes</h3>
            @for (item of invalidRelationEntries(); track item.artifactKey) {
              <div class="observation-item">
                <p>
                  <strong>{{ item.artifactKey }}</strong> · {{ item.values.join(', ') }}
                </p>
                <button class="btn text" type="button" (click)="reviewArtifact(item.artifactKey)">
                  Revisar <app-icon name="arrow" />
                </button>
              </div>
            }
          </article>
        }
        @if (
          (store.validation()?.user_stories_with_invalid_format?.length ?? 0) > 0 ||
          (store.validation()?.user_stories_without_acceptance_criteria?.length ?? 0) > 0
        ) {
          <article class="alert-card">
            <span class="pill amber">Historias de usuario</span>
            <h3>Historias que requieren ajuste estructural</h3>
            <div class="observation-actions">
              @for (artifactKey of invalidUserStoryKeys(); track artifactKey) {
                <button class="btn text" type="button" (click)="reviewArtifact(artifactKey)">
                  Revisar {{ artifactKey }} <app-icon name="arrow" />
                </button>
              }
            </div>
          </article>
        }
      } @else {
        @if (store.run(); as run) {
          <div class="notice">
            <app-icon name="check" />
            <div>
              <strong>Ejecución reproducible registrada</strong><br />La configuración queda
              asociada al resultado generado.
            </div>
          </div>
          <div class="run-summary gap">
            <div>
              <small>Modelo LLM</small
              ><strong>{{
                run.parameters.experimental_config?.llm?.model ||
                  run.parameters.model ||
                  'No registrado'
              }}</strong>
            </div>
            <div>
              <small>Embeddings</small
              ><strong>{{
                run.parameters.experimental_config?.embedding?.model || 'No registrado'
              }}</strong>
            </div>
            <div>
              <small>Recuperación</small
              ><strong
                >RRF · top {{ run.parameters.experimental_config?.retrieval?.top_k || '—' }}</strong
              >
            </div>
            <div>
              <small>Reranking</small
              ><strong>{{
                run.parameters.experimental_config?.reranker?.enabled
                  ? (run.parameters.experimental_config?.reranker?.provider === 'jev' ? 'Jev · OpenRouter' : 'Local')
                  : 'Desactivado'
              }}</strong>
            </div>
            <div>
              <small>Versión de prompts</small
              ><strong>{{
                run.parameters.experimental_config?.prompt_version || 'No registrada'
              }}</strong>
            </div>
            <div>
              <small>Intentos LLM</small
              ><strong>{{ run.parameters.metrics?.total_attempts || '—' }}</strong>
            </div>
            <div>
              <small>Latencia LLM acumulada</small
              ><strong>{{ formatLatency(run.parameters.metrics?.total_latency_ms) }}</strong>
            </div>
            <div>
              <small>Tokens registrados · proyecto</small
              ><strong>{{ formatTokens(store.tokenUsage()?.total_tokens) }}</strong>
              @if (store.tokenUsage(); as usage) {
                <small>Fuentes: {{ formatTokens(usage.by_phase.sources) }} · Definición: {{ formatTokens(usage.by_phase.definition) }}</small>
                <small>Generación: {{ formatTokens(usage.by_phase.generation) }} · Jev: {{ formatTokens(usage.by_phase.jev) }}</small>
                <small>Revisiones: {{ formatTokens(usage.by_phase.revision) }} · Validación semántica: {{ formatTokens(usage.by_phase.semantic_validation) }}</small>
                @if (usage.unreported_runs) { <small>{{ usage.unreported_runs }} ejecuciones antiguas sin telemetría completa.</small> }
              }
            </div>
          </div>
          <p class="stage-desc">
            Estos datos documentan cómo se produjo esta salida; no sustituyen la evaluación de
            calidad por expertos.
          </p>
        } @else {
          <p class="empty-filter">Todavía no existe una ejecución registrada.</p>
        }
      }

      <div class="stage-footer sticky-actions">
        <small
          >Los vínculos permiten localizar la fuente;<br />la pertinencia de la evidencia requiere
          tu revisión.</small
        ><button class="btn primary" type="button" (click)="openExport()">
          Preparar exportación <app-icon name="arrow" />
        </button>
      </div>
    </div>

    @if (approvalWarningOpen()) {
      <div class="modal-backdrop" (click)="approvalWarningOpen.set(false)">
        <section
          class="modal-card confirm-dialog"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="approve-all-title"
          (click)="$event.stopPropagation()"
        >
          <button
            class="icon-btn modal-close"
            type="button"
            (click)="approvalWarningOpen.set(false)"
            aria-label="Cerrar"
          >
            ×
          </button>
          <span class="pill amber">Decisión masiva</span>
          <h2 id="approve-all-title">¿Aprobar todos los artefactos?</h2>
          <p>
            Se marcarán como aprobados {{ remainingApprovalCount() }} artefactos que actualmente no
            lo están, incluidos los que estén propuestos, requieran aclaración o hayan sido
            descartados.
          </p>
          <div class="notice amber gap">
            <app-icon name="warning" />
            <div>
              <strong>Las observaciones automáticas no desaparecerán.</strong><br />Esta acción
              registra tu decisión humana, pero no garantiza que la redacción, clasificación o
              trazabilidad sean correctas. Cada cambio quedará en el historial.
            </div>
          </div>
          <div class="actions">
            <button class="btn" type="button" (click)="approvalWarningOpen.set(false)">
              Cancelar
            </button>
            <button class="btn primary" type="button" (click)="approveAll()" [disabled]="busy()">
              Sí, aprobar todo
            </button>
          </div>
        </section>
      </div>
    }
  `,
})
export class ReviewStageComponent implements OnInit {
  readonly store = inject(WorkspaceStore);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly tab = signal<ReviewTab>('artifacts');
  readonly filter = signal<ArtifactFilter>('Todos');
  readonly approvalWarningOpen = signal(false);
  readonly busy = signal(false);
  readonly filters: ArtifactFilter[] = ['Todos', 'RF', 'RNF', 'HU', 'Aprobados'];
  readonly filtered = computed(() =>
    this.store
      .artifacts()
      .filter(
        (item) =>
          this.filter() === 'Todos' ||
          item.artifact_type === this.filter() ||
          (this.filter() === 'Aprobados' && item.status === 'aceptado'),
      ),
  );
  ngOnInit(): void {
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const requestedTab = params.get('tab');
      this.tab.set(
        requestedTab === 'trace' || requestedTab === 'alerts' || requestedTab === 'run'
          ? requestedTab
          : 'artifacts',
      );
      const type = params.get('type');
      this.filter.set(type === 'RF' || type === 'RNF' || type === 'HU' ? type : 'Todos');
    });
  }
  remainingApprovalCount(): number {
    return this.store.artifacts().filter((item) => item.status !== 'aceptado').length;
  }
  filterLabel(item: ArtifactFilter): string {
    const counts = this.store.counts();
    const count =
      item === 'Todos'
        ? this.store.artifacts().length
        : item === 'Aprobados'
          ? this.store.artifacts().filter((artifact) => artifact.status === 'aceptado').length
          : counts[item];
    return `${item} (${count})`;
  }
  openView(tab: ReviewTab, type?: 'RF' | 'RNF' | 'HU'): void {
    const project = this.store.project();
    if (!project) return;
    void this.router.navigate(['/projects', project.id, 'review'], {
      queryParams: { tab, ...(type ? { type } : {}) },
    });
  }
  async approveAll(): Promise<void> {
    const project = this.store.project();
    if (!project || this.remainingApprovalCount() === 0) return;
    this.busy.set(true);
    try {
      await firstValueFrom(this.api.approveAllArtifacts(project.id));
      this.approvalWarningOpen.set(false);
      await this.store.refreshProject();
    } catch (error) {
      this.store.setError(this.store.message(error));
    } finally {
      this.busy.set(false);
    }
  }
  pendingCount(): number {
    return this.store
      .artifacts()
      .filter((item) => item.status === 'propuesto' || item.status === 'requiere aclaración')
      .length;
  }
  citedCount(): number {
    return this.store.artifacts().filter((item) => item.source_fragments.length > 0).length;
  }
  invalidCitations(): string[] {
    return Object.entries(this.store.validation()?.invalid_citations ?? {}).flatMap(
      ([artifact, citations]) => citations.map((citation) => `${artifact}: ${citation}`),
    );
  }
  invalidRelations(): string[] {
    return Object.entries(this.store.validation()?.invalid_relations ?? {}).flatMap(
      ([artifact, relations]) => relations.map((relation) => `${artifact}: ${relation}`),
    );
  }
  invalidCitationEntries(): Array<{ artifactKey: string; values: string[] }> {
    return Object.entries(this.store.validation()?.invalid_citations ?? {}).map(
      ([artifactKey, values]) => ({ artifactKey, values }),
    );
  }
  invalidRelationEntries(): Array<{ artifactKey: string; values: string[] }> {
    return Object.entries(this.store.validation()?.invalid_relations ?? {}).map(
      ([artifactKey, values]) => ({ artifactKey, values }),
    );
  }
  invalidUserStoryKeys(): string[] {
    const report = this.store.validation();
    return Array.from(
      new Set([
        ...(report?.user_stories_with_invalid_format ?? []),
        ...(report?.user_stories_without_acceptance_criteria ?? []),
      ]),
    );
  }
  alertCount(): number {
    const report = this.store.validation();
    return (
      (report?.artifacts_without_citations.length ?? 0) +
      this.invalidCitations().length +
      (report?.possible_duplicates.length ?? 0) +
      (report?.cross_type_duplicates?.length ?? 0) +
      this.invalidRelations().length +
      (report?.user_stories_with_invalid_format?.length ?? 0) +
      (report?.user_stories_without_acceptance_criteria?.length ?? 0) +
      (report?.taxonomy_warnings.length ?? 0)
    );
  }
  statusLabel(status: Artifact['status']): string {
    return (
      {
        propuesto: 'Propuesto',
        'requiere aclaración': 'Requiere aclaración',
        aceptado: 'Aprobado',
        rechazado: 'Descartado',
      } as Record<string, string>
    )[status];
  }
  inspectCitation(artifact: Artifact, citation: string): void {
    this.store.selectedArtifact.set(artifact);
    void this.store.selectFragment(citation);
  }
  selectRelated(artifactKey: string): void {
    const artifact = this.store.artifacts().find((item) => item.artifact_key === artifactKey);
    if (artifact) this.store.selectArtifact(artifact);
  }
  reviewArtifact(artifactKey: string): void {
    const artifact = this.store.artifacts().find((item) => item.artifact_key === artifactKey);
    if (!artifact) return;
    this.openView('artifacts');
    this.store.selectArtifact(artifact);
  }
  formatLatency(value?: number): string {
    return value == null ? '—' : `${(value / 1000).toFixed(1)} s`;
  }
  formatTokens(value?: number): string {
    return value == null ? '—' : value.toLocaleString('es-EC');
  }
  openExport(): void {
    const project = this.store.project();
    if (project) void this.router.navigate(['/projects', project.id, 'export']);
  }
}
