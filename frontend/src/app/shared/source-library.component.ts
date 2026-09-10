import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../core/api.service';
import { Source } from '../core/models';
import { WorkspaceStore } from '../core/workspace.store';
import { IconComponent } from './icon.component';
import { SourceDocumentDialogComponent } from './source-document-dialog.component';

@Component({
  selector: 'app-source-library',
  imports: [FormsModule, IconComponent, SourceDocumentDialogComponent],
  template: `
    <aside class="panel sources-panel">
      <div class="panel-head"><h2><app-icon name="file" /> Fuentes <span class="muted">{{ store.sources().length || '' }}</span></h2><button class="icon-btn" type="button" aria-label="Mostrar u ocultar fuentes"><app-icon name="book" /></button></div>
      <div class="panel-body">
        <button class="btn full" type="button" (click)="uploadOpen.set(true)"><app-icon name="plus" /> Añadir fuentes</button>
        @if (store.sources().length === 0) {
          <div class="source-empty"><app-icon name="file" /><h3 style="font-size:13px">Aún no hay fuentes</h3><p>Añade el contexto, las entrevistas y las reglas de tu proyecto.</p></div>
        } @else {
          <p class="source-intro">Contexto documental del proyecto</p>
          @for (source of store.sources(); track source.id) {
            <div class="source-entry">
              <button class="source" [class.active]="store.selectedFragment()?.source_code === source.source_code" type="button" (click)="inspectSource(source.source_code)">
                <span class="file-icon"><app-icon name="file" /></span>
                <span class="grow"><strong>{{ source.original_name }}</strong><small>{{ source.source_code }} · {{ typeLabel(source.content_type, source.original_name, source.source_kind) }}</small></span>
                @if (source.status === 'indexed') { <span class="check">✓</span> }
              </button>
              <button class="icon-btn source-action" type="button" title="Visualizar documento" [attr.aria-label]="'Visualizar ' + source.original_name" (click)="openSource(source, 'preview')"><app-icon name="eye" /></button>
              <button class="icon-btn source-action danger" type="button" title="Eliminar fuente" [attr.aria-label]="'Eliminar ' + source.original_name" (click)="openSource(source, 'delete')"><app-icon name="trash" /></button>
            </div>
          }
          @if (store.project()?.definition_confirmed) {
            <hr class="divider"><p class="eyebrow">Aclaraciones del usuario</p>
            <button class="source" type="button" (click)="inspectDefinition()"><app-icon name="chat" /><span><strong>Definición confirmada</strong><small>USR-DEF · decisiones del usuario</small></span></button>
          }
        }
      </div>
      <div class="source-footer"><app-icon name="shield" /> {{ store.sources().length ? 'Fuentes listas para consultar. Cada fragmento conserva su procedencia.' : 'Tus documentos son el punto de partida de todo el proceso.' }}<br><span style="display:block;margin-top:10px">{{ store.project()?.fragment_count ?? 0 }} fragmentos indexados</span></div>
    </aside>
    @if (uploadOpen()) {
      <div class="modal-backdrop" (click)="closeUpload()"><div class="modal-card" (click)="$event.stopPropagation()">
        <button class="icon-btn modal-close" type="button" (click)="closeUpload()" aria-label="Cerrar">×</button><h2>Añadir fuentes</h2><p>Sube un documento o pega directamente el contenido de un correo, entrevista, conversación o nota.</p>
        <div class="segmented source-mode"><button type="button" [class.active]="inputMode() === 'files'" (click)="inputMode.set('files')">Subir archivos</button><button type="button" [class.active]="inputMode() === 'text'" (click)="inputMode.set('text')">Pegar texto</button></div>
        @if (inputMode() === 'files') {
          <div class="dropzone"><app-icon name="upload" /><h3>Arrastra archivos o selecciónalos</h3><p>PDF con texto · DOCX · TXT · Markdown</p><button class="btn soft" type="button" (click)="sourceInput.click()">Seleccionar archivos</button><input #sourceInput type="file" accept=".pdf,.docx,.txt,.md" multiple hidden (change)="selectFiles($event)"></div>
          @for (file of files(); track file.name) { <div class="file-row"><app-icon name="file" /><div class="grow">{{ file.name }}<br><small>{{ formatBytes(file.size) }} · listo para procesar</small></div><span class="pill purple">Seleccionado</span></div> }
        } @else {
          <div class="text-source-form"><div class="form-grid"><label><span class="form-label">Tipo de fuente</span><select [(ngModel)]="textType"><option value="email">Correo electrónico</option><option value="interview">Entrevista transcrita</option><option value="meeting_notes">Notas de reunión</option><option value="conversation">Conversación</option><option value="note">Nota libre</option><option value="other">Otro texto</option></select></label><label><span class="form-label">Título</span><input [(ngModel)]="textTitle" placeholder="Ej.: Correo del responsable comercial"></label></div><label><span class="form-label">Contenido textual</span><textarea class="source-textarea" [(ngModel)]="textContent" placeholder="Pega aquí el texto tal como lo recibiste. No necesita encabezados ni una estructura especial."></textarea></label><small class="muted">ReqLab conservará este contenido como una fuente independiente y trazable.</small></div>
        }
        @if (uploadErrors().length) { <div class="alert error gap">@for (message of uploadErrors(); track message) { <div>{{ message }}</div> }</div> }
        <div class="actions"><button class="btn" type="button" (click)="closeUpload()">Cerrar</button>@if (inputMode() === 'files') { <button class="btn primary" type="button" (click)="upload()" [disabled]="!files().length || uploading()">@if (uploading()) { <span class="spinner small"></span> Procesando } @else { Procesar fuentes }</button> } @else { <button class="btn primary" type="button" (click)="saveText()" [disabled]="textTitle.trim().length < 2 || textContent.trim().length < 20 || uploading()">@if (uploading()) { <span class="spinner small"></span> Procesando } @else { Guardar fuente textual }</button> }</div>
      </div></div>
    }
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
export class SourceLibraryComponent {
  readonly store = inject(WorkspaceStore);
  private readonly api = inject(ApiService);
  readonly uploadOpen = signal(false);
  readonly files = signal<File[]>([]);
  readonly uploading = signal(false);
  readonly uploadErrors = signal<string[]>([]);
  readonly inputMode = signal<'files' | 'text'>('files');
  readonly selectedSource = signal<Source | null>(null);
  readonly dialogMode = signal<'preview' | 'delete'>('preview');
  textTitle = '';
  textType = 'email';
  textContent = '';
  async inspectSource(sourceCode: string): Promise<void> {
    const project = this.store.project(); if (!project) return;
    try {
      const fragments = await firstValueFrom(this.api.listFragments(project.id, sourceCode));
      if (fragments[0]) await this.store.selectFragment(fragments[0].fragment_key);
    } catch (error) { this.store.setError(this.store.message(error)); }
  }
  async inspectDefinition(): Promise<void> { await this.inspectSource('USR-DEF'); }
  openSource(source: Source, mode: 'preview' | 'delete'): void { this.dialogMode.set(mode); this.selectedSource.set(source); }
  async sourceDeleted(projectId: string): Promise<void> { this.store.clearDetail(); await this.store.loadWorkspace(projectId); }
  selectFiles(event: Event): void { this.files.set(Array.from((event.target as HTMLInputElement).files ?? [])); this.uploadErrors.set([]); }
  closeUpload(): void { if (!this.uploading()) { this.uploadOpen.set(false); this.resetInput(); } }
  async upload(): Promise<void> {
    const project = this.store.project(); if (!project) return; this.uploading.set(true); this.uploadErrors.set([]);
    try {
      const result = await firstValueFrom(this.api.uploadSources(project.id, this.files()));
      this.uploadErrors.set(result.errors.map((item) => `${item.filename}: ${item.detail}`));
      await this.store.loadWorkspace(project.id);
      if (!result.errors.length) this.closeUpload();
    } catch (error) { this.uploadErrors.set([this.store.message(error)]); }
    finally { this.uploading.set(false); if (!this.uploadErrors().length) { this.uploadOpen.set(false); this.files.set([]); } }
  }
  async saveText(): Promise<void> {
    const project = this.store.project(); if (!project) return; this.uploading.set(true); this.uploadErrors.set([]);
    try {
      await firstValueFrom(this.api.createTextSource(project.id, { title: this.textTitle, source_type: this.textType, text: this.textContent }));
      await this.store.loadWorkspace(project.id); this.uploadOpen.set(false); this.resetInput();
    } catch (error) { this.uploadErrors.set([this.store.message(error)]); }
    finally { this.uploading.set(false); }
  }
  private resetInput(): void { this.files.set([]); this.uploadErrors.set([]); this.inputMode.set('files'); this.textTitle = ''; this.textType = 'email'; this.textContent = ''; }
  formatBytes(value: number): string { return value < 1024 * 1024 ? `${Math.ceil(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`; }
  typeLabel(contentType: string, filename = '', sourceKind = 'document'): string {
    const sourceLabels: Record<string, string> = { email: 'Correo', interview: 'Entrevista', meeting_notes: 'Reunión', conversation: 'Conversación', note: 'Nota', other: 'Texto pegado' };
    if (sourceLabels[sourceKind]) return sourceLabels[sourceKind];
    const value = `${contentType} ${filename}`.toLowerCase();
    if (value.includes('pdf')) return 'PDF';
    if (value.includes('word') || value.endsWith('.docx')) return 'DOCX';
    if (value.includes('markdown') || value.endsWith('.md')) return 'Markdown';
    return 'Texto';
  }
}
