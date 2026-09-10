import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { Project } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { IconComponent } from '../../shared/icon.component';
import { TopbarComponent } from '../../shared/topbar.component';

@Component({
  selector: 'app-project-list',
  imports: [FormsModule, IconComponent, TopbarComponent],
  template: `
    <app-topbar (settingsRequested)="openArchived()" />
    <main class="landing">
      <section class="hero">
        <div>
          <div class="eyebrow">De la evidencia a la especificación</div>
          <h1>Tus fuentes.<br />Tus próximos <span>requisitos.</span></h1>
          <p>
            Un espacio para entender el contexto, construir requisitos y seguir el hilo de cada
            decisión.
          </p>
          <div class="gap">
            <button class="btn primary" type="button" (click)="showForm.set(true)">
              <app-icon name="plus" /> Crear proyecto
            </button>
          </div>
        </div>
        <div class="hero-art" aria-hidden="true">
          <div class="art-sheet">
            <app-icon name="file" />
            <div class="art-line"></div>
            <div class="art-line"></div>
            <div class="art-line short"></div>
            <div class="art-line"></div>
            <div class="art-line short"></div>
          </div>
          <app-icon name="arrow" />
          <div class="art-output">
            <div><b>RF</b> Qué debe hacer <app-icon name="check" /></div>
            <div><b>RNF</b> Con qué calidad</div>
            <div><b>HU</b> Para quién</div>
          </div>
          <small>CADA PROPUESTA, CON SU EVIDENCIA</small>
        </div>
      </section>
      <div class="row between">
        <h2 style="font-size:20px">Tus proyectos</h2>
        <small class="muted">{{ store.projects().length }} proyectos</small>
      </div>
      <div class="projects-toolbar">
        <div class="segmented" aria-label="Filtrar proyectos">
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
        <label class="search"
          ><app-icon name="search" /><input
            [(ngModel)]="query"
            placeholder="Buscar un proyecto"
            aria-label="Buscar proyectos"
        /></label>
      </div>
      @if (store.error()) {
        <div class="alert error">{{ store.error() }}</div>
      }
      <div class="project-grid">
        <button class="project-card new" type="button" (click)="showForm.set(true)">
          <span class="project-icon"><app-icon name="plus" /></span>
          <h3>Un nuevo comienzo</h3>
          <p>Crea un proyecto y añade<br />tus primeras fuentes.</p>
        </button>
        @for (project of filteredProjects(); track project.id; let index = $index) {
          <article
            class="project-card"
            [class.purple]="index % 3 === 1"
            [class.sand]="index % 3 === 2"
          >
            <button class="project-card-main" type="button" (click)="open(project.id)" [attr.aria-label]="'Abrir proyecto ' + project.name">
              <span class="project-icon"><app-icon [name]="projectIcon(project)" /></span>
              <span
                class="pill"
                [class.green]="projectPhase(project) === 3"
                [class.purple]="projectPhase(project) === 1"
                [class.outline]="projectPhase(project) !== 1 && projectPhase(project) !== 3"
                >{{ phaseNames[projectPhase(project)] }}</span
              >
              <h3>{{ project.name }}</h3>
              <p>{{ project.source_count }} fuentes · {{ project.artifact_count }} artefactos</p>
              <footer><span>{{ updatedLabel(project.updated_at) }}</span></footer>
            </button>
            <div class="project-card-actions">
              <app-icon class="icon-btn" name="arrow" title="Abrir proyecto" [attr.aria-label]="'Abrir proyecto' + project.name" (click)="open(project.id)"/>
              <app-icon class="icon-btn" name="archive" title="Archivar proyecto" [attr.aria-label]="'Archivar ' + project.name" (click)="archive(project)"/>
              <app-icon class="icon-btn danger" name="trash" title="Eliminar proyecto" [attr.aria-label]="'Eliminar ' + project.name" (click)="requestDelete(project)"/>
            </div>
          </article>
        }
      </div>
      @if (!store.loading() && filteredProjects().length === 0) {
        <p class="empty-filter">No hay proyectos que coincidan con este filtro.</p>
      }
      <div class="landing-note">
        <span><app-icon name="shield" /> Tu revisión mantiene el control de cada propuesta.</span
        ><span>Persistencia de fuentes por proyecto</span>
      </div>
    </main>

    @if (showForm()) {
      <div class="modal-backdrop" (click)="showForm.set(false)">
        <form class="modal-card" (click)="$event.stopPropagation()" (ngSubmit)="create()">
          <button
            class="icon-btn modal-close"
            type="button"
            (click)="showForm.set(false)"
            aria-label="Cerrar"
          >
            ×
          </button>
          <h2>Crear un proyecto</h2>
          <p class="muted small-gap">
            Empieza con un espacio vacío para las fuentes de un solo proyecto.
          </p>
          <label class="form-label gap">Nombre del proyecto</label
          ><input
            name="name"
            [(ngModel)]="draft.name"
            required
            maxlength="160"
            autofocus
            placeholder="Ej. Sistema de gestión de solicitudes"
          />
          <label class="form-label gap">Dominio <span class="muted">(opcional)</span></label
          ><input
            name="domain"
            [(ngModel)]="draft.domain"
            maxlength="240"
            placeholder="Ej. educación superior"
          />
          <label class="form-label gap"
            >Descripción breve <span class="muted">(opcional)</span></label
          ><textarea
            name="description"
            [(ngModel)]="draft.description"
            maxlength="1000"
            placeholder="¿Qué problema busca resolver?"
          ></textarea>
          <div class="actions">
            <button class="btn" type="button" (click)="showForm.set(false)">Cancelar</button
            ><button
              class="btn primary"
              type="submit"
              [disabled]="store.loading() || draft.name.trim().length < 2"
            >
              Crear proyecto <app-icon name="arrow" />
            </button>
          </div>
        </form>
      </div>
    }

    @if (archivedOpen() && !projectToDelete()) {
      <div class="modal-backdrop" (click)="archivedOpen.set(false)">
        <section class="modal-card archived-dialog" role="dialog" aria-modal="true" aria-labelledby="archived-title" (click)="$event.stopPropagation()">
          <button class="icon-btn modal-close" type="button" (click)="archivedOpen.set(false)" aria-label="Cerrar">×</button>
          <h2 id="archived-title">Proyectos archivados</h2>
          <p>Estos proyectos conservan sus fuentes, definiciones y artefactos. Puedes devolverlos a la lista principal.</p>
          @if (store.error()) { <div class="alert error">{{ store.error() }}</div> }
          <div class="archived-list">
            @for (project of store.archivedProjects(); track project.id) {
              <div class="archived-project-row">
                <span class="project-icon"><app-icon name="archive" /></span>
                <div class="grow"><strong>{{ project.name }}</strong><small>{{ project.source_count }} fuentes · archivado {{ updatedLabel(project.archived_at || project.updated_at) }}</small></div>
                <button class="btn soft" type="button" (click)="restore(project)" [disabled]="store.loading()"><app-icon name="restore" /> Desarchivar</button>
                <button class="icon-btn danger" type="button" title="Eliminar proyecto" [attr.aria-label]="'Eliminar ' + project.name" (click)="requestDelete(project)"><app-icon name="trash" /></button>
              </div>
            } @empty {
              <div class="archived-empty"><app-icon name="archive" /><p>No hay proyectos archivados.</p></div>
            }
          </div>
          <div class="actions"><button class="btn primary" type="button" (click)="archivedOpen.set(false)">Cerrar</button></div>
        </section>
      </div>
    }

    @if (projectToDelete(); as project) {
      <div class="modal-backdrop" (click)="projectToDelete.set(null)">
        <section class="modal-card confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-project-title" (click)="$event.stopPropagation()">
          <button class="icon-btn modal-close" type="button" (click)="projectToDelete.set(null)" aria-label="Cerrar">×</button>
          <div class="delete-confirmation">
            <app-icon name="warning" />
            <div><h2 id="delete-project-title">Eliminar proyecto</h2><p>Se eliminará definitivamente “{{ project.name }}” junto con sus fuentes, definiciones, artefactos e historial de revisiones. Esta acción no se puede deshacer.</p></div>
          </div>
          @if (store.error()) { <div class="alert error">{{ store.error() }}</div> }
          <div class="actions">
            <button class="btn" type="button" (click)="projectToDelete.set(null)" [disabled]="store.loading()">Cancelar</button>
            <button class="btn danger" type="button" (click)="deleteConfirmed(project)" [disabled]="store.loading()">@if (store.loading()) { <span class="spinner small"></span> Eliminando } @else { <app-icon name="trash" /> Eliminar definitivamente }</button>
          </div>
        </section>
      </div>
    }
  `,
})
export class ProjectListComponent implements OnInit {
  readonly store = inject(WorkspaceStore);
  private readonly router = inject(Router);
  readonly showForm = signal(false);
  readonly archivedOpen = signal(false);
  readonly projectToDelete = signal<Project | null>(null);
  readonly filter = signal<'Todos' | 'En curso' | 'Exportados'>('Todos');
  readonly filters: Array<'Todos' | 'En curso' | 'Exportados'> = [
    'Todos',
    'En curso',
    'Exportados',
  ];
  readonly phaseNames = ['Fuentes', 'Definición', 'Generación', 'Revisión', 'Exportación'];
  query = '';
  draft = { name: '', domain: '', description: '' };
  filteredProjects(): Project[] {
    const query = this.query.trim().toLowerCase();
    return this.store.projects().filter((item) => {
      const matchesQuery =
        !query || `${item.name} ${item.domain} ${item.description}`.toLowerCase().includes(query);
      const matchesFilter =
        this.filter() === 'Todos' ||
        (this.filter() === 'Exportados' ? item.status === 'exported' : item.status !== 'exported');
      return matchesQuery && matchesFilter;
    });
  }
  ngOnInit(): void {
    void this.store.loadProjects();
  }
  open(id: string): void {
    void this.router.navigate(['/projects', id, 'sources']);
  }
  async create(): Promise<void> {
    const project = await this.store.createProject(this.draft);
    if (project) {
      this.showForm.set(false);
      await this.router.navigate(['/projects', project.id, 'sources']);
    }
  }
  async openArchived(): Promise<void> {
    this.archivedOpen.set(true);
    await this.store.loadArchivedProjects();
  }
  async archive(project: Project): Promise<void> {
    await this.store.setProjectArchived(project.id, true);
  }
  async restore(project: Project): Promise<void> {
    await this.store.setProjectArchived(project.id, false);
  }
  requestDelete(project: Project): void {
    this.store.clearError();
    this.projectToDelete.set(project);
  }
  async deleteConfirmed(project: Project): Promise<void> {
    const completed = await this.store.deleteProject(project.id);
    if (completed) this.projectToDelete.set(null);
  }
  projectPhase(project: Project): number {
    if (project.status === 'exported') return 4;
    if (project.artifact_count > 0 || project.status === 'review') return 3;
    if (project.status === 'generating') return 2;
    if (project.definition_confirmed || project.status === 'ready_to_generate') return 2;
    if (project.source_count > 0) return 1;
    return 0;
  }
  projectIcon(project: Project): string {
    const phase = this.projectPhase(project);
    return phase === 0 ? 'folder' : phase === 1 ? 'chat' : 'layers';
  }
  updatedLabel(value: string): string {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? 'Actualizado'
      : date.toLocaleDateString('es-EC', { day: '2-digit', month: 'short' });
  }
}
