import { Component, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { WorkspaceStore } from '../../core/workspace.store';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-export-stage',
  imports: [IconComponent],
  template: `
    <div class="stage-body export-stage">
      <div class="stage-label"><app-icon name="spark" /> Una entrega con contexto</div><h2>Prepara los resultados</h2><p class="stage-desc">Exporta los artefactos junto con sus fuentes, estados de revisión y decisiones. La entrega conserva la diferencia entre una propuesta y un requisito aprobado.</p>
      @if (!allApproved() || alertCount()) { <div class="notice amber gap"><app-icon name="warning" /><div><strong>La entrega se identificará como borrador</strong><br>{{ store.artifacts().length - approvedCount() }} artefactos sin aprobación. {{ alertCount() }} observaciones automáticas pendientes. Puedes exportar el avance con sus estados actuales.</div></div> }
      @else { <div class="notice gap"><app-icon name="check" /><div>Todos los artefactos están aprobados y no existen alertas estructurales pendientes.</div></div> }

      <h3 class="gap" style="font-size:13px">Formato de entrega</h3>
      <label class="format-card"><input type="radio" name="format" value="json" [checked]="format() === 'json'" (change)="format.set('json')"><app-icon name="layers" /><span><strong>JSON</strong><small>Datos estructurados, referencias, versiones y validación.</small></span></label>
      <label class="format-card"><input type="radio" name="format" value="docx" [checked]="format() === 'docx'" (change)="format.set('docx')"><app-icon name="file" /><span><strong>Documento Word (.docx)</strong><small>Documento editable con definición, artefactos y trazabilidad.</small></span></label>

      <div class="summary-list"><div><span>Contenido</span><strong>{{ store.artifacts().length }} artefactos · {{ approvedCount() }} aprobados</strong></div><div><span>Evidencia documental</span><strong>{{ store.sources().length }} fuentes con fragmentos</strong></div><div><span>Aclaraciones</span><strong>{{ store.questions().length }} respuestas de definición</strong></div><div><span>Incluye</span><strong>Estados, citas y observaciones</strong></div></div>
      <div class="stage-footer"><small>La exportación utiliza las versiones vigentes<br>almacenadas para este proyecto.</small>@if (store.project(); as project) { <a class="btn primary" [href]="api.exportUrl(project.id, format())"><app-icon name="download" /> Descargar {{ format().toUpperCase() }}</a> }</div>
    </div>
  `,
})
export class ExportStageComponent {
  readonly store = inject(WorkspaceStore);
  readonly api = inject(ApiService);
  readonly format = signal<'json' | 'docx'>('docx');
  approvedCount(): number { return this.store.artifacts().filter((item) => item.status === 'aceptado').length; }
  allApproved(): boolean { return this.store.artifacts().length > 0 && this.approvedCount() === this.store.artifacts().length; }
  alertCount(): number { const report = this.store.validation(); return (report?.artifacts_without_citations.length ?? 0) + Object.values(report?.invalid_citations ?? {}).reduce((sum, items) => sum + items.length, 0) + (report?.possible_duplicates.length ?? 0) + (report?.taxonomy_warnings.length ?? 0) + (report?.requirements_without_verification_criteria?.length ?? 0) + (report?.requirements_with_invalid_ears?.length ?? 0) + (report?.non_functional_measurement_pending?.length ?? 0) + (report?.undefined_priorities?.length ?? 0) + (report?.priorities_without_source?.length ?? 0); }
}
