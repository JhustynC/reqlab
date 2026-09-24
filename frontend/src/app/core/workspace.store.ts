import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService } from './api.service';
import { Artifact, DefinitionQuestion, FragmentDetail, GenerationRun, Project, ProjectTokenUsage, RerankingSettings, RevisionProposal, Source, ValidationReport } from './models';

@Injectable({ providedIn: 'root' })
export class WorkspaceStore {
  private readonly api = inject(ApiService);
  readonly projects = signal<Project[]>([]);
  readonly archivedProjects = signal<Project[]>([]);
  readonly project = signal<Project | null>(null);
  readonly sources = signal<Source[]>([]);
  readonly questions = signal<DefinitionQuestion[]>([]);
  readonly artifacts = signal<Artifact[]>([]);
  readonly selectedArtifact = signal<Artifact | null>(null);
  readonly selectedFragment = signal<FragmentDetail | null>(null);
  readonly validation = signal<ValidationReport | null>(null);
  readonly run = signal<GenerationRun | null>(null);
  readonly tokenUsage = signal<ProjectTokenUsage | null>(null);
  readonly rerankingSettings = signal<RerankingSettings | null>(null);
  readonly proposal = signal<RevisionProposal | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly counts = computed(() => ({
    RF: this.artifacts().filter((item) => item.artifact_type === 'RF').length,
    RNF: this.artifacts().filter((item) => item.artifact_type === 'RNF').length,
    HU: this.artifacts().filter((item) => item.artifact_type === 'HU').length,
  }));

  async loadProjects(): Promise<void> { await this.perform(async () => this.projects.set(await firstValueFrom(this.api.listProjects()))); }
  async loadArchivedProjects(): Promise<void> {
    await this.perform(async () => this.archivedProjects.set(await firstValueFrom(this.api.listProjects(true))));
  }
  async loadRerankingSettings(): Promise<void> {
    await this.perform(async () => this.rerankingSettings.set(await firstValueFrom(this.api.getRerankingSettings())));
  }
  async saveRerankingSettings(value: Pick<RerankingSettings, 'enabled' | 'provider'>): Promise<boolean> {
    let saved = false;
    await this.perform(async () => {
      this.rerankingSettings.set(await firstValueFrom(this.api.saveRerankingSettings(value)));
      saved = true;
    });
    return saved;
  }
  async createProject(payload: { name: string; description: string; domain: string }): Promise<Project | null> {
    let created: Project | null = null;
    await this.perform(async () => { created = await firstValueFrom(this.api.createProject(payload)); });
    if (created) await this.loadProjects();
    return created;
  }
  async loadWorkspace(projectId: string): Promise<void> {
    await this.perform(async () => {
      const [project, sources, questions, artifacts, validation, latestRun, tokenUsage] = await Promise.all([
        firstValueFrom(this.api.getProject(projectId)), firstValueFrom(this.api.listSources(projectId)),
        firstValueFrom(this.api.listQuestions(projectId)), firstValueFrom(this.api.listArtifacts(projectId)),
        firstValueFrom(this.api.latestValidation(projectId)),
        firstValueFrom(this.api.latestRun(projectId)),
        firstValueFrom(this.api.getProjectTokenUsage(projectId)),
      ]);
      this.project.set(project); this.sources.set(sources); this.questions.set(questions);
      this.artifacts.set(artifacts); this.validation.set(validation.report);
      this.run.set(latestRun.run);
      this.tokenUsage.set(tokenUsage);
      const selectedId = this.selectedArtifact()?.id;
      this.selectedArtifact.set(artifacts.find((item) => item.id === selectedId) ?? null);
    });
  }
  async refreshProject(): Promise<void> { const id = this.project()?.id; if (id) await this.loadWorkspace(id); }
  async setProjectArchived(projectId: string, archived: boolean): Promise<boolean> {
    let completed = false;
    await this.perform(async () => {
      await firstValueFrom(this.api.setProjectArchived(projectId, archived));
      const [active, archivedItems] = await Promise.all([
        firstValueFrom(this.api.listProjects()), firstValueFrom(this.api.listProjects(true)),
      ]);
      this.projects.set(active); this.archivedProjects.set(archivedItems); completed = true;
    });
    return completed;
  }
  async deleteProject(projectId: string): Promise<boolean> {
    let completed = false;
    await this.perform(async () => {
      await firstValueFrom(this.api.deleteProject(projectId));
      const [active, archivedItems] = await Promise.all([
        firstValueFrom(this.api.listProjects()), firstValueFrom(this.api.listProjects(true)),
      ]);
      this.projects.set(active); this.archivedProjects.set(archivedItems); completed = true;
    });
    return completed;
  }
  async selectFragment(fragmentKey: string): Promise<void> {
    const id = this.project()?.id; if (!id) return;
    await this.perform(async () => this.selectedFragment.set(await firstValueFrom(this.api.getFragment(id, fragmentKey))));
  }
  selectArtifact(artifact: Artifact): void { this.selectedArtifact.set(artifact); this.clearEvidence(); }
  clearDetail(): void { this.selectedArtifact.set(null); this.clearEvidence(); }
  clearEvidence(): void { this.selectedFragment.set(null); }
  setError(message: string): void { this.error.set(message); }
  clearError(): void { this.error.set(''); }
  private async perform(operation: () => Promise<void>): Promise<void> {
    this.loading.set(true); this.error.set('');
    try { await operation(); } catch (error) { this.error.set(this.message(error)); } finally { this.loading.set(false); }
  }
  message(error: unknown): string {
    if (typeof error === 'object' && error && 'error' in error) {
      const response = (error as { error?: { detail?: unknown; message?: unknown } | string }).error;
      if (typeof response === 'string' && response.trim()) return response;
      if (response && typeof response === 'object') {
        const detail = response.detail;
        if (typeof detail === 'string' && detail.trim()) return detail;
        if (Array.isArray(detail)) {
          const messages = detail.map((item) => this.validationMessage(item)).filter(Boolean);
          if (messages.length) return messages.join(' · ');
        }
        if (typeof response.message === 'string' && response.message.trim()) {
          return response.message;
        }
      }
    }
    return error instanceof Error ? error.message : 'No se pudo completar la operación.';
  }

  private validationMessage(detail: unknown): string {
    if (typeof detail === 'string') return detail;
    if (!detail || typeof detail !== 'object') return '';
    const issue = detail as { loc?: unknown; msg?: unknown; message?: unknown };
    const rawLocation = Array.isArray(issue.loc) ? issue.loc : [];
    const location = rawLocation
      .filter((part) => part !== 'body')
      .map((part) => String(part))
      .join(' › ');
    const description =
      typeof issue.msg === 'string'
        ? issue.msg
        : typeof issue.message === 'string'
          ? issue.message
          : 'Valor no valido.';
    return location ? `${location}: ${description}` : description;
  }
}
