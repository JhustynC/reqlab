import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Artifact } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { IconComponent } from '../../shared/icon.component';

type ReviewTab = 'artifacts' | 'trace' | 'alerts';
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
        <button type="button" [class.active]="tab() === 'artifacts'" (click)="tab.set('artifacts')">
          Artefactos</button
        ><button type="button" [class.active]="tab() === 'trace'" (click)="tab.set('trace')">
          Trazabilidad</button
        ><button type="button" [class.active]="tab() === 'alerts'" (click)="tab.set('alerts')">
          Observaciones ({{ alertCount() }})
        </button>
      </div>

      @if (tab() === 'artifacts') {
        <div class="row between wrap" style="margin-bottom:15px">
          <small class="muted"
            >{{ store.artifacts().length }} propuestas · {{ pendingCount() }} por revisar</small
          ><small style="font-size:10px;color:var(--mint);display:flex;align-items:center;gap:8px"
            ><app-icon name="link" /> {{ citedCount() }} con fuente vinculada</small
          >
        </div>
        <div class="filter-row">
          @for (item of filters; track item) {
            <button
              type="button"
              [class.active]="filter() === item"
              (click)="filter.set(item)"
              [attr.aria-pressed]="filter() === item"
            >
              {{ item }}
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
            @if (artifact.acceptance_criteria.length) {
              <ul class="criteria">
                @for (criterion of artifact.acceptance_criteria; track criterion) {
                  <li>{{ criterion }}</li>
                }
              </ul>
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
                  <td>{{ statusLabel(artifact.status) }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <div class="row between">
          <small class="muted">{{ alertCount() }} observaciones automáticas</small
          ><span class="pill amber">Revisión humana</span>
        </div>
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
            <p>{{ store.validation()?.artifacts_without_citations?.join(', ') }}</p>
          </article>
        }
        @if (invalidCitations().length) {
          <article class="alert-card">
            <span class="pill amber">Referencia inválida</span>
            <h3>Citas que no existen en el corpus</h3>
            <p>{{ invalidCitations().join(', ') }}</p>
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
                {{ item.left }} / {{ item.right }} · {{ (item.jaccard * 100).toFixed(0) }}%<br />
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
                {{ item.artifact_id }} · {{ item.reason }}<br />
              }
            </p>
          </article>
        }
      }

      <div class="stage-footer">
        <small
          >Los vínculos permiten localizar la fuente;<br />la pertinencia de la evidencia requiere
          tu revisión.</small
        ><button class="btn primary" type="button" (click)="openExport()">
          Preparar exportación <app-icon name="arrow" />
        </button>
      </div>
    </div>
  `,
})
export class ReviewStageComponent implements OnInit {
  readonly store = inject(WorkspaceStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly tab = signal<ReviewTab>('artifacts');
  readonly filter = signal<ArtifactFilter>('Todos');
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
    const type = this.route.snapshot.queryParamMap.get('type');
    if (type === 'RF' || type === 'RNF' || type === 'HU') this.filter.set(type);
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
  alertCount(): number {
    const report = this.store.validation();
    return (
      (report?.artifacts_without_citations.length ?? 0) +
      this.invalidCitations().length +
      (report?.possible_duplicates.length ?? 0) +
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
  openExport(): void {
    const project = this.store.project();
    if (project) void this.router.navigate(['/projects', project.id, 'export']);
  }
}
