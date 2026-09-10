import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Phase, Project } from '../core/models';

@Component({
  selector: 'app-phase-stepper',
  imports: [RouterLink],
  template: `
    <nav class="stepper" aria-label="Fases del proceso">
      @for (item of phases; track item.key; let index = $index) {
        <a class="step" [class.current]="phase() === item.key" [class.done]="isDone(index)" [class.disabled]="!accessible(item.key)"
           [routerLink]="accessible(item.key) ? ['/projects', project().id, item.key] : null"
           [attr.aria-disabled]="!accessible(item.key)">
          <span class="num">@if (isDone(index)) { <span aria-hidden="true">✓</span> } @else { {{ index + 1 }} }</span>
          <span><strong>{{ item.label }}</strong><small>{{ item.caption }}</small></span>
        </a>
      }
    </nav>
  `,
})
export class PhaseStepperComponent {
  readonly project = input.required<Project>();
  readonly phase = input.required<Phase>();
  readonly phases: Array<{ key: Phase; label: string; caption: string }> = [
    { key: 'sources', label: 'Fuentes', caption: 'Prepara el contexto' },
    { key: 'definition', label: 'Definición', caption: 'Aclara el alcance' },
    { key: 'generation', label: 'Generación', caption: 'Construye propuestas' },
    { key: 'review', label: 'Revisión', caption: 'Revisa la evidencia' },
    { key: 'export', label: 'Exportación', caption: 'Comparte resultados' },
  ];
  accessible(phase: Phase): boolean {
    if (phase === 'sources') return true;
    if (phase === 'definition') return this.project().source_count > 0;
    if (phase === 'generation') return Boolean(this.project().definition_confirmed);
    return this.project().artifact_count > 0;
  }
  isDone(index: number): boolean {
    const current = this.phases.findIndex((item) => item.key === this.phase());
    return index < current && this.accessible(this.phases[index].key);
  }
}
