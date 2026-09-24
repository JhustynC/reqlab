import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { DefinitionQuestion, GenerationRun } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-definition-stage',
  imports: [FormsModule, IconComponent],
  template: `
    <div class="stage-body definition-stage">
      <div class="stage-label"><app-icon name="spark" /> Antes de generar</div>
      <h2>Confirma qué entendió ReqLab</h2>
      <p class="stage-desc">
        ReqLab interpreta las fuentes sin exigir una plantilla previa. Después te muestra una
        definición provisional y pregunta solamente por vacíos, ambigüedades, contradicciones o
        decisiones relevantes.
      </p>

      @if (!hasAnalysis()) {
        <div class="notice gap">
          <app-icon name="book" />
          <div>
            <strong>El corpus aún no ha sido interpretado</strong><br />El análisis recorrerá los
            {{ store.project()?.fragment_count ?? 0 }} fragmentos disponibles; no se limita a los
            primeros documentos ni a los primeros fragmentos.
          </div>
        </div>
        <div class="definition-start">
          <app-icon name="spark" />
          <h3>Construir interpretación provisional</h3>
          <p>
            Identificaremos objetivo, problema, actores, alcance, exclusiones, reglas, expectativas
            de calidad y posibles conflictos, siempre con referencias a las fuentes.
          </p>
          <button class="btn primary" type="button" (click)="analyze()" [disabled]="busy()">
            @if (busy()) {
              <span class="spinner small"></span> Analizando todo el corpus
            } @else {
              Analizar corpus <app-icon name="arrow" />
            }
          </button>
          @if (busy()) {
            <div class="grow" style="width: min(100%, 620px)">
              <div class="row between gap">
                <small class="muted">{{ definitionRun()?.parameters?.message || 'Preparando el análisis…' }}</small>
                <span class="pill purple">{{ definitionProgress() }} %</span>
              </div>
              <div
                class="progress"
                role="progressbar"
                aria-label="Progreso del análisis del corpus"
                aria-valuemin="0"
                aria-valuemax="100"
                [attr.aria-valuenow]="definitionProgress()"
              >
                <div [style.width.%]="definitionProgress()"></div>
              </div>
            </div>
          }
          @if (definitionRun()?.status === 'failed') {
            <div class="alert error">
              {{ definitionRun()?.error_message || 'No se pudo completar el análisis del corpus.' }}
            </div>
          }
        </div>
      } @else {
        <div class="notice gap">
          <app-icon name="check" />
          <div>
            <strong>Análisis completo del corpus</strong><br />Se recorrieron
            {{ coverage()?.fragment_count ?? store.project()?.fragment_count ?? 0 }} fragmentos
            @if (coverage()) {
              en {{ coverage()?.batch_count }} bloque(s) de análisis
            }
            . Revisa la interpretación y corrige cualquier dato antes de confirmarla.
          </div>
        </div>
        <div class="row between gap definition-toolbar">
          <div>
            <h3>Interpretación provisional</h3>
            <small class="muted"
              >Los campos son editables; una inferencia de ReqLab nunca sustituye tu
              confirmación.</small
            >
          </div>
          <button class="btn soft" type="button" (click)="analyze()" [disabled]="busy()">
            <app-icon name="spark" /> Analizar nuevamente
          </button>
        </div>

        <form (ngSubmit)="save()">
          @for (question of coreQuestions(); track question.question_key; let index = $index) {
            <article class="question provisional-card">
              <div class="question-head">
                <span class="eyebrow">{{ twoDigits(index + 1) }} · Interpretación del corpus</span
                ><span
                  class="pill"
                  [class.green]="question.confidence === 'high'"
                  [class.amber]="question.confidence === 'medium'"
                  [class.red]="question.confidence === 'low' || question.confidence === 'missing'"
                  >{{ confidenceLabel(question.confidence) }}</span
                >
              </div>
              <h3>{{ question.question }}</h3>
              <p>{{ question.rationale }}</p>
              <label class="form-label" [for]="question.question_key"
                >Interpretación provisional</label
              ><textarea
                [id]="question.question_key"
                [name]="question.question_key"
                [(ngModel)]="answers[question.question_key]"
                placeholder="No se encontró información suficiente. Puedes completarla o responder la pregunta de aclaración asociada."
              ></textarea>
              <div class="evidence-row">
                <small class="muted">Evidencia:</small>
                @if (question.evidence.length) {
                  @for (citation of question.evidence; track citation) {
                    <button class="citation" type="button" (click)="showEvidence(citation)">
                      <app-icon name="link" /> {{ citation }}
                    </button>
                  }
                } @else {
                  <span class="pill outline">Sin evidencia suficiente</span>
                }
              </div>
            </article>
          }

          <div class="definition-section-head">
            <span class="eyebrow">Aclaraciones necesarias</span>
            <h3>Preguntas adaptativas</h3>
            <p>Solo aparecen preguntas que el corpus no permitió resolver con claridad.</p>
          </div>
          @if (!dynamicQuestions().length) {
            <div class="notice">
              <app-icon name="check" />
              <div>
                <strong>No hay aclaraciones obligatorias</strong><br />Puedes corregir la
                interpretación provisional si lo necesitas y confirmarla.
              </div>
            </div>
          }
          @for (question of dynamicQuestions(); track question.question_key; let index = $index) {
            <article class="question clarification-card">
              <div class="question-head">
                <span class="eyebrow">{{ twoDigits(index + 1) }} · Vacío o decisión detectada</span
                ><span
                  class="pill"
                  [class.green]="(answers[question.question_key] ?? '').trim()"
                  [class.purple]="!(answers[question.question_key] ?? '').trim()"
                  >{{
                    (answers[question.question_key] ?? '').trim()
                      ? 'Respondida'
                      : 'Requiere tu respuesta'
                  }}</span
                >
              </div>
              <h3>{{ question.question }}</h3>
              <p>{{ question.rationale }}</p>
              <label class="form-label" [for]="question.question_key"
                >Tu respuesta <span class="required">*</span></label
              ><textarea
                [id]="question.question_key"
                [name]="question.question_key"
                [(ngModel)]="answers[question.question_key]"
                placeholder="Escribe una decisión concreta…"
              ></textarea>
              @if (question.evidence.length) {
                <div class="evidence-row">
                  <small class="muted">Contexto:</small>
                  @for (citation of question.evidence; track citation) {
                    <button class="citation" type="button" (click)="showEvidence(citation)">
                      <app-icon name="link" /> {{ citation }}
                    </button>
                  }
                </div>
              }
            </article>
          }
          @if (missingCount()) {
            <div class="notice amber gap">
              <app-icon name="warning" />
              <div>
                <strong>{{ missingCount() }} aclaración(es) pendiente(s)</strong><br />Puedes
                guardar el avance; la generación se habilitará al responderlas y confirmar la
                interpretación.
              </div>
            </div>
          }
          <footer class="stage-footer sticky-actions">
            <small>{{
              store.project()?.definition_confirmed
                ? 'Definición confirmada. Si la editas, deberás confirmarla de nuevo.'
                : 'La generación se habilita al confirmar esta interpretación.'
            }}</small>
            <div class="row">
              <button class="btn" type="submit" [disabled]="busy()">Guardar</button
              ><button
                class="btn primary"
                type="button"
                (click)="confirm()"
                [disabled]="busy() || missingCount() > 0"
              >
                Confirmar definición <app-icon name="arrow" />
              </button>
            </div>
          </footer>
        </form>
      }
    </div>

    @if (resetWarningOpen()) {
      <div class="modal-backdrop" (click)="resetWarningOpen.set(false)">
        <section
          class="modal-card confirm-dialog"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="reset-generation-title"
          (click)="$event.stopPropagation()"
        >
          <button
            class="icon-btn modal-close"
            type="button"
            (click)="resetWarningOpen.set(false)"
            aria-label="Cerrar"
          >
            ×
          </button>
          <span class="pill amber">Resultados existentes</span>
          <h2 id="reset-generation-title">¿Confirmar nuevamente la definición?</h2>
          <p>
            Ya existen {{ store.artifacts().length }} artefactos generados. Para evitar mezclar
            resultados de dos definiciones, se eliminarán los artefactos, sus versiones, las
            observaciones y los registros de generación actuales.
          </p>
          <div class="notice amber gap">
            <app-icon name="warning" />
            <div>
              <strong>Las fuentes y tus respuestas se conservarán.</strong><br />La etapa de
              generación volverá a empezar desde cero con la definición que acabas de revisar.
            </div>
          </div>
          <div class="actions">
            <button class="btn" type="button" (click)="resetWarningOpen.set(false)">
              Cancelar
            </button>
            <button
              class="btn primary"
              type="button"
              (click)="confirmAndReset()"
              [disabled]="busy()"
            >
              Confirmar y reiniciar generación
            </button>
          </div>
        </section>
      </div>
    }
  `,
})
export class DefinitionStageComponent implements OnInit, OnDestroy {
  readonly store = inject(WorkspaceStore);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly busy = signal(false);
  readonly resetWarningOpen = signal(false);
  readonly coverage = signal<{ fragment_count: number; batch_count: number } | null>(null);
  readonly definitionRun = signal<GenerationRun | null>(null);
  private timer?: ReturnType<typeof setTimeout>;
  answers: Record<string, string> = {};

  ngOnInit(): void {
    this.syncAnswers();
    void this.resumeDefinitionRun();
  }
  ngOnDestroy(): void {
    if (this.timer) clearTimeout(this.timer);
  }
  coreQuestions(): DefinitionQuestion[] {
    return this.store.questions().filter((item) => item.origin === 'core');
  }
  dynamicQuestions(): DefinitionQuestion[] {
    return this.store.questions().filter((item) => item.origin === 'dynamic');
  }
  hasAnalysis(): boolean {
    return this.coreQuestions().some((item) => Boolean(item.confidence));
  }
  private syncAnswers(): void {
    for (const item of this.store.questions()) this.answers[item.question_key] = item.answer;
  }
  missingCount(): number {
    return this.dynamicQuestions().filter(
      (item) => item.required && !(this.answers[item.question_key] ?? '').trim(),
    ).length;
  }
  twoDigits(value: number): string {
    return String(value).padStart(2, '0');
  }
  confidenceLabel(value: DefinitionQuestion['confidence']): string {
    return (
      {
        high: 'Confianza alta',
        medium: 'Confianza media',
        low: 'Confianza baja',
        missing: 'Información ausente',
        pending: 'Pendiente',
        '': 'Sin analizar',
      }[value] ?? 'Sin analizar'
    );
  }
  async showEvidence(fragmentKey: string): Promise<void> {
    await this.store.selectFragment(fragmentKey);
  }
  async analyze(): Promise<void> {
    const project = this.store.project();
    if (!project) return;
    this.busy.set(true);
    this.store.clearError();
    try {
      const result = await firstValueFrom(this.api.analyzeDefinition(project.id));
      await this.pollDefinition(result.run_id);
    } catch (error) {
      this.store.setError(this.store.message(error));
      this.busy.set(false);
    }
  }
  definitionProgress(): number {
    return this.definitionRun()?.parameters?.progress ?? 0;
  }
  private async resumeDefinitionRun(): Promise<void> {
    const project = this.store.project();
    if (!project || this.hasAnalysis()) return;
    try {
      const result = await firstValueFrom(this.api.latestDefinitionRun(project.id));
      this.definitionRun.set(result.run);
      if (result.run?.status === 'running') {
        this.busy.set(true);
        await this.pollDefinition(result.run.id);
      }
    } catch {
      // La consulta de reanudación no bloquea el uso normal de la etapa.
    }
  }
  private async pollDefinition(runId: string): Promise<void> {
    try {
      const run = await firstValueFrom(this.api.getRun(runId));
      this.definitionRun.set(run);
      if (run.status === 'completed') {
        this.busy.set(false);
        this.coverage.set(
          run.parameters.metrics?.coverage ?? {
            fragment_count: this.store.project()?.fragment_count ?? 0,
            batch_count: 0,
          },
        );
        this.answers = {};
        await this.store.refreshProject();
        this.syncAnswers();
        return;
      }
      if (run.status === 'failed') {
        this.busy.set(false);
        this.store.setError(run.error_message || 'No se pudo completar el análisis del corpus.');
        return;
      }
      this.timer = setTimeout(() => void this.pollDefinition(runId), 1200);
    } catch (error) {
      this.store.setError(this.store.message(error));
      this.busy.set(false);
    }
  }
  async save(): Promise<boolean> {
    const project = this.store.project();
    if (!project) return false;
    this.busy.set(true);
    try {
      const result = await firstValueFrom(
        this.api.saveAnswers(
          project.id,
          Object.entries(this.answers).map(([question_key, answer]) => ({ question_key, answer })),
        ),
      );
      this.store.questions.set(result.questions);
      return true;
    } catch (error) {
      this.store.setError(this.store.message(error));
      return false;
    } finally {
      this.busy.set(false);
    }
  }
  async confirm(): Promise<void> {
    const project = this.store.project();
    if (!project || !this.hasAnalysis()) return;
    if (this.store.artifacts().length) {
      this.resetWarningOpen.set(true);
      return;
    }
    await this.performConfirmation(false);
  }
  async confirmAndReset(): Promise<void> {
    this.resetWarningOpen.set(false);
    await this.performConfirmation(true);
  }
  private async performConfirmation(resetGeneration: boolean): Promise<void> {
    const project = this.store.project();
    if (!project || !(await this.save())) return;
    this.busy.set(true);
    try {
      await firstValueFrom(this.api.confirmDefinition(project.id, resetGeneration));
      await this.store.loadWorkspace(project.id);
      await this.router.navigate(['/projects', project.id, 'generation']);
    } catch (error) {
      this.store.setError(this.store.message(error));
    } finally {
      this.busy.set(false);
    }
  }
}
