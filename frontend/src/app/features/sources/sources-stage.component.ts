import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Source } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { IconComponent } from '../../shared/icon.component';
import { SourceDocumentDialogComponent } from '../../shared/source-document-dialog.component';

@Component({
  selector: 'app-sources-stage',
  imports: [FormsModule, IconComponent, SourceDocumentDialogComponent],
  template: `
    <div class="stage-body">
      @if (!store.sources().length) { <div class="stage-icon"><app-icon name="folder" /></div> }
      <div class="stage-label"><app-icon name="spark" /> {{ store.sources().length ? 'El contexto está listo' : 'Tu espacio de trabajo' }}</div>
      <h2>{{ store.sources().length ? 'Todo empieza por las fuentes' : 'Dale contexto a tu proyecto' }}</h2>
      <p class="stage-desc">{{ store.sources().length ? 'Revisa qué documentos formarán parte del análisis antes de definir el sistema.' : 'Reúne la información que describe el sistema. Te ayudaremos a convertirla en propuestas de requisitos respaldadas por evidencia.' }}</p>

      @if (store.sources().length) {
        <div class="notice gap"><app-icon name="check" /><div><strong>{{ store.sources().length }} fuentes disponibles</strong><br>Los documentos se procesaron con la misma canalización y cada fragmento conserva su procedencia.</div></div>
        @for (source of store.sources(); track source.id) {
          <div class="file-row">
            <app-icon name="file" />
            <div class="grow">{{ source.original_name }}<br><small>{{ source.source_code }} · {{ source.status }}</small></div>
            <span class="pill green">Lista</span>
            <button class="icon-btn row-action" type="button" title="Visualizar documento" [attr.aria-label]="'Visualizar ' + source.original_name" (click)="openSource(source, 'preview')"><app-icon name="eye" /></button>
            <button class="icon-btn row-action danger" type="button" title="Eliminar fuente" [attr.aria-label]="'Eliminar ' + source.original_name" (click)="openSource(source, 'delete')"><app-icon name="trash" /></button>
          </div>
        }
      }

      @if (!store.sources().length) {
        <div class="segmented source-mode stage-source-mode"><button type="button" [class.active]="inputMode() === 'files'" (click)="inputMode.set('files')">Subir archivos</button><button type="button" [class.active]="inputMode() === 'text'" (click)="inputMode.set('text')">Pegar texto</button></div>
        @if (inputMode() === 'files') {
          <div class="dropzone" [class.dragging]="dragging()" (dragover)="dragOver($event)" (dragleave)="dragging.set(false)" (drop)="drop($event)"><app-icon name="upload" /><h3>Arrastra tus archivos aquí</h3><p>Contexto del sistema, entrevistas transcritas,<br>procesos o reglas de negocio.</p><button class="btn soft" type="button" (click)="fileInput.click()">Seleccionar archivos</button><input #fileInput type="file" multiple accept=".pdf,.docx,.txt,.md" (change)="selectFiles($event)" hidden><small>PDF con texto · DOCX · TXT · Markdown</small></div>
        } @else {
          <div class="text-source-form standalone"><div class="form-grid"><label><span class="form-label">Tipo de fuente</span><select [(ngModel)]="textType"><option value="email">Correo electrónico</option><option value="interview">Entrevista transcrita</option><option value="meeting_notes">Notas de reunión</option><option value="conversation">Conversación</option><option value="note">Nota libre</option><option value="other">Otro texto</option></select></label><label><span class="form-label">Título</span><input [(ngModel)]="textTitle" placeholder="Ej.: Entrevista con la persona usuaria"></label></div><label><span class="form-label">Contenido textual</span><textarea class="source-textarea" [(ngModel)]="textContent" placeholder="Pega el contenido sin darle un formato especial. ReqLab lo segmentará y conservará su procedencia."></textarea></label></div>
        }
      }
      @if (files().length) {
        @for (file of files(); track file.name) { <div class="file-row"><app-icon name="file" /><div class="grow">{{ file.name }}<br><small>{{ formatBytes(file.size) }} · listo para procesar</small></div><span class="pill purple">Seleccionado</span></div> }
      }
      @if (uploadErrors().length) {
        <div class="alert error">@for (message of uploadErrors(); track message) { <div>{{ message }}</div> }</div>
      }
      @if (!store.sources().length) { <div class="notice"><app-icon name="eye" /><div>Los PDF deben contener texto seleccionable. El texto pegado puede conservar el formato informal de un correo, nota o entrevista transcrita.</div></div> }
      <footer class="stage-footer">
        <small>{{ store.sources().length ? 'Siguiente: aclarar el objetivo y los límites.' : 'Añade al menos una fuente para continuar.' }}</small>
        @if (inputMode() === 'files' && files().length) { <button class="btn primary" type="button" (click)="upload()" [disabled]="uploading()">@if (uploading()) { <span class="spinner small"></span> Procesando } @else { Procesar fuentes <app-icon name="arrow" /> }</button> }
        @else if (inputMode() === 'text' && !store.sources().length) { <button class="btn primary" type="button" (click)="saveText()" [disabled]="textTitle.trim().length < 2 || textContent.trim().length < 20 || uploading()">@if (uploading()) { <span class="spinner small"></span> Procesando } @else { Guardar texto y continuar <app-icon name="arrow" /> }</button> }
        @else if (store.sources().length) { <button class="btn primary" type="button" (click)="continueToDefinition()">Continuar a definición <app-icon name="arrow" /></button> }
      </footer>
    </div>
    @if (store.project(); as project) {
      <app-source-document-dialog
        [projectId]="project.id"
        [source]="selectedSource()"
        [mode]="dialogMode()"
        (closed)="selectedSource.set(null)"
        (deleted)="sourceDeleted(project.id)"
      />
    }
  `,
})
export class SourcesStageComponent {
  readonly store = inject(WorkspaceStore);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly files = signal<File[]>([]);
  readonly uploading = signal(false);
  readonly uploadErrors = signal<string[]>([]);
  readonly dragging = signal(false);
  readonly inputMode = signal<'files' | 'text'>('files');
  readonly selectedSource = signal<Source | null>(null);
  readonly dialogMode = signal<'preview' | 'delete'>('preview');
  textTitle = '';
  textType = 'email';
  textContent = '';
  selectFiles(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.files.set(Array.from(input.files ?? []));
    this.uploadErrors.set([]);
  }
  dragOver(event: DragEvent): void { event.preventDefault(); this.dragging.set(true); }
  drop(event: DragEvent): void { event.preventDefault(); this.dragging.set(false); this.files.set(Array.from(event.dataTransfer?.files ?? [])); this.uploadErrors.set([]); }
  async upload(): Promise<void> {
    const project = this.store.project(); if (!project) return;
    this.uploading.set(true); this.uploadErrors.set([]);
    try {
      const result = await firstValueFrom(this.api.uploadSources(project.id, this.files()));
      this.uploadErrors.set(result.errors.map((item) => `${item.filename}: ${item.detail}`));
      this.files.set([]);
      await this.store.loadWorkspace(project.id);
      if (result.accepted.length && !result.errors.length) await this.router.navigate(['/projects', project.id, 'definition']);
    } catch (error) { this.store.setError(this.store.message(error)); }
    finally { this.uploading.set(false); }
  }
  async saveText(): Promise<void> {
    const project = this.store.project(); if (!project) return; this.uploading.set(true); this.uploadErrors.set([]);
    try {
      await firstValueFrom(this.api.createTextSource(project.id, { title: this.textTitle, source_type: this.textType, text: this.textContent }));
      await this.store.loadWorkspace(project.id); await this.router.navigate(['/projects', project.id, 'definition']);
    } catch (error) { this.uploadErrors.set([this.store.message(error)]); }
    finally { this.uploading.set(false); }
  }
  continueToDefinition(): void { const project = this.store.project(); if (project) void this.router.navigate(['/projects', project.id, 'definition']); }
  openSource(source: Source, mode: 'preview' | 'delete'): void { this.dialogMode.set(mode); this.selectedSource.set(source); }
  async sourceDeleted(projectId: string): Promise<void> { await this.store.loadWorkspace(projectId); }
  formatBytes(value: number): string { return value < 1024 * 1024 ? `${Math.ceil(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`; }
}
