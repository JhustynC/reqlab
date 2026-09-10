import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../core/api.service';
import { Source, SourcePreview } from '../core/models';
import { IconComponent } from './icon.component';

@Component({
  selector: 'app-source-document-dialog',
  imports: [IconComponent],
  template: `
    @if (source) {
      <div class="modal-backdrop" (click)="close()">
        <section class="modal-card document-dialog" role="dialog" aria-modal="true" aria-labelledby="source-dialog-title" (click)="$event.stopPropagation()">
          <button class="icon-btn modal-close" type="button" (click)="close()" aria-label="Cerrar">×</button>
          <div class="document-dialog-title">
            <span class="file-icon"><app-icon name="file" /></span>
            <div>
              <h2 id="source-dialog-title">{{ source.original_name }}</h2>
              <p>{{ source.source_code }} · {{ typeLabel(source) }}</p>
            </div>
          </div>

          @if (confirmingDelete()) {
            <div class="delete-confirmation">
              <app-icon name="warning" />
              <div>
                <h3>Eliminar esta fuente</h3>
                <p>Se eliminarán el archivo y sus fragmentos. Si el proyecto ya tenía una definición confirmada o artefactos generados, también se reiniciarán porque podrían citar evidencia que dejará de existir.</p>
              </div>
            </div>
            @if (error()) { <div class="alert error">{{ error() }}</div> }
            <div class="actions">
              <button class="btn" type="button" (click)="cancelDelete()" [disabled]="deleting()">Cancelar</button>
              <button class="btn danger" type="button" (click)="remove()" [disabled]="deleting()">
                @if (deleting()) { <span class="spinner small"></span> Eliminando } @else { <app-icon name="trash" /> Eliminar definitivamente }
              </button>
            </div>
          } @else {
            @if (loading()) {
              <div class="document-loading"><span class="spinner"></span><span>Preparando vista previa…</span></div>
            } @else if (error()) {
              <div class="alert error">{{ error() }}</div>
            } @else if (preview()) {
              <div class="document-meta">
                <span>{{ preview()!.fragment_count }} fragmentos</span>
                <span>{{ preview()!.character_count.toLocaleString('es-EC') }} caracteres</span>
                <span>Contenido extraído</span>
              </div>
              <pre class="document-preview-text">{{ preview()!.text }}</pre>
            }
            <div class="actions between-actions">
              <button class="btn danger text" type="button" (click)="confirmingDelete.set(true)"><app-icon name="trash" /> Eliminar fuente</button>
              <button class="btn primary" type="button" (click)="close()">Cerrar</button>
            </div>
          }
        </section>
      </div>
    }
  `,
})
export class SourceDocumentDialogComponent implements OnChanges {
  private readonly api = inject(ApiService);
  @Input({ required: true }) projectId = '';
  @Input() source: Source | null = null;
  @Input() mode: 'preview' | 'delete' = 'preview';
  @Output() readonly closed = new EventEmitter<void>();
  @Output() readonly deleted = new EventEmitter<Source>();

  readonly preview = signal<SourcePreview | null>(null);
  readonly loading = signal(false);
  readonly deleting = signal(false);
  readonly confirmingDelete = signal(false);
  readonly error = signal('');

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['source'] && !changes['mode']) return;
    this.preview.set(null);
    this.error.set('');
    this.confirmingDelete.set(this.mode === 'delete');
    if (this.source && this.mode === 'preview') void this.loadPreview(this.source);
  }

  async loadPreview(source: Source): Promise<void> {
    this.loading.set(true);
    try {
      const preview = await firstValueFrom(this.api.previewSource(this.projectId, source.id));
      if (this.source?.id === source.id) this.preview.set(preview);
    } catch (error) {
      this.error.set(this.message(error));
    } finally {
      this.loading.set(false);
    }
  }

  async remove(): Promise<void> {
    if (!this.source) return;
    const deleted = this.source;
    this.deleting.set(true);
    this.error.set('');
    try {
      await firstValueFrom(this.api.deleteSource(this.projectId, deleted.id));
      this.deleted.emit(deleted);
      this.close();
    } catch (error) {
      this.error.set(this.message(error));
    } finally {
      this.deleting.set(false);
    }
  }

  cancelDelete(): void {
    if (this.mode === 'delete') this.close();
    else this.confirmingDelete.set(false);
  }

  close(): void {
    if (!this.deleting()) this.closed.emit();
  }

  typeLabel(source: Source): string {
    const sourceLabels: Record<string, string> = { email: 'Correo electrónico', interview: 'Entrevista transcrita', meeting_notes: 'Notas de reunión', conversation: 'Conversación', note: 'Nota libre', other: 'Texto pegado' };
    if (sourceLabels[source.source_kind]) return sourceLabels[source.source_kind];
    const value = `${source.content_type} ${source.original_name}`.toLowerCase();
    if (value.includes('pdf')) return 'PDF';
    if (value.includes('word') || value.endsWith('.docx')) return 'DOCX';
    if (value.includes('markdown') || value.endsWith('.md')) return 'Markdown';
    return 'Texto';
  }

  private message(error: unknown): string {
    if (typeof error === 'object' && error && 'error' in error) {
      const response = (error as { error?: { detail?: string } }).error;
      if (response?.detail) return response.detail;
    }
    return error instanceof Error ? error.message : 'No se pudo completar la operación.';
  }
}
