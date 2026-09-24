import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  Artifact,
  ArtifactType,
  DefinitionAnalysis,
  DefinitionQuestion,
  FragmentDetail,
  FragmentSummary,
  GenerationLimits,
  GenerationRecommendations,
  GenerationRun,
  Project,
  ProjectTokenUsage,
  RerankingSettings,
  RevisionProposal,
  Source,
  SourcePreview,
  ValidationReport,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api';

  listProjects(archived = false): Observable<Project[]> {
    const params = archived ? new HttpParams().set('archived', true) : undefined;
    return this.http.get<Project[]>(`${this.base}/projects`, { params });
  }
  getProject(projectId: string): Observable<Project> {
    return this.http.get<Project>(`${this.base}/projects/${projectId}`);
  }
  getRerankingSettings(): Observable<RerankingSettings> {
    return this.http.get<RerankingSettings>(`${this.base}/projects/settings/reranking`);
  }
  saveRerankingSettings(value: Pick<RerankingSettings, 'enabled' | 'provider'>): Observable<RerankingSettings> {
    return this.http.put<RerankingSettings>(`${this.base}/projects/settings/reranking`, value);
  }
  getProjectTokenUsage(projectId: string): Observable<ProjectTokenUsage> {
    return this.http.get<ProjectTokenUsage>(`${this.base}/projects/${projectId}/token-usage`);
  }
  createProject(payload: {
    name: string;
    description: string;
    domain: string;
  }): Observable<Project> {
    return this.http.post<Project>(`${this.base}/projects`, payload);
  }
  listSources(projectId: string): Observable<Source[]> {
    return this.http.get<Source[]>(`${this.base}/projects/${projectId}/sources`);
  }
  uploadSources(
    projectId: string,
    files: File[],
  ): Observable<{
    accepted: Source[];
    errors: Array<{ filename: string; detail: string }>;
    fragment_count: number;
  }> {
    const form = new FormData();
    files.forEach((file) => form.append('files', file, file.name));
    return this.http.post<{
      accepted: Source[];
      errors: Array<{ filename: string; detail: string }>;
      fragment_count: number;
    }>(`${this.base}/projects/${projectId}/sources`, form);
  }
  createTextSource(
    projectId: string,
    payload: { title: string; source_type: string; text: string },
  ): Observable<Source> {
    return this.http.post<Source>(`${this.base}/projects/${projectId}/sources/text`, payload);
  }
  previewSource(projectId: string, sourceId: string): Observable<SourcePreview> {
    return this.http.get<SourcePreview>(
      `${this.base}/projects/${projectId}/sources/${sourceId}/preview`,
    );
  }
  deleteSource(projectId: string, sourceId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/projects/${projectId}/sources/${sourceId}`);
  }
  setProjectArchived(projectId: string, archived: boolean): Observable<Project> {
    return this.http.patch<Project>(`${this.base}/projects/${projectId}/archive`, { archived });
  }
  deleteProject(projectId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/projects/${projectId}`);
  }
  listFragments(projectId: string, sourceCode?: string): Observable<FragmentSummary[]> {
    const params = sourceCode ? new HttpParams().set('source_code', sourceCode) : undefined;
    return this.http.get<FragmentSummary[]>(`${this.base}/projects/${projectId}/fragments`, {
      params,
    });
  }
  getFragment(projectId: string, fragmentKey: string): Observable<FragmentDetail> {
    return this.http.get<FragmentDetail>(
      `${this.base}/projects/${projectId}/fragments/${encodeURIComponent(fragmentKey)}`,
    );
  }
  listQuestions(projectId: string): Observable<DefinitionQuestion[]> {
    return this.http.get<DefinitionQuestion[]>(
      `${this.base}/projects/${projectId}/definition/questions`,
    );
  }
  analyzeDefinition(
    projectId: string,
  ): Observable<{ analysis: DefinitionAnalysis; questions: DefinitionQuestion[] }> {
    return this.http.post<{ analysis: DefinitionAnalysis; questions: DefinitionQuestion[] }>(
      `${this.base}/projects/${projectId}/definition/analyze`,
      {},
    );
  }
  saveAnswers(
    projectId: string,
    answers: Array<{ question_key: string; answer: string }>,
  ): Observable<{ questions: DefinitionQuestion[] }> {
    return this.http.put<{ questions: DefinitionQuestion[] }>(
      `${this.base}/projects/${projectId}/definition/answers`,
      { answers },
    );
  }
  confirmDefinition(
    projectId: string,
    resetGeneration = false,
  ): Observable<{ profile: Record<string, unknown>; generation_reset: boolean }> {
    return this.http.post<{ profile: Record<string, unknown>; generation_reset: boolean }>(
      `${this.base}/projects/${projectId}/definition/confirm`,
      { reset_generation: resetGeneration },
    );
  }
  startGeneration(
    projectId: string,
    limits: GenerationLimits,
  ): Observable<{ run_id: string; status: string; limits: GenerationLimits }> {
    return this.http.post<{ run_id: string; status: string; limits: GenerationLimits }>(
      `${this.base}/projects/${projectId}/generation`,
      { limits },
    );
  }
  generationRecommendations(projectId: string): Observable<GenerationRecommendations> {
    return this.http.get<GenerationRecommendations>(
      `${this.base}/projects/${projectId}/generation/recommendations`,
    );
  }
  getRun(runId: string): Observable<GenerationRun> {
    return this.http.get<GenerationRun>(`${this.base}/runs/${runId}`);
  }
  latestRun(projectId: string): Observable<{ run: GenerationRun | null }> {
    return this.http.get<{ run: GenerationRun | null }>(
      `${this.base}/projects/${projectId}/runs/latest`,
    );
  }
  listArtifacts(projectId: string, artifactType?: ArtifactType): Observable<Artifact[]> {
    const params = artifactType ? new HttpParams().set('artifact_type', artifactType) : undefined;
    return this.http.get<Artifact[]>(`${this.base}/projects/${projectId}/artifacts`, { params });
  }
  updateArtifact(projectId: string, artifact: Artifact): Observable<Artifact> {
    return this.http.put<Artifact>(`${this.base}/projects/${projectId}/artifacts/${artifact.id}`, {
      artifact_type: artifact.artifact_type,
      title: artifact.title,
      description: artifact.description,
      priority: artifact.priority,
      status: artifact.status,
      source_fragments: artifact.source_fragments,
      acceptance_criteria: artifact.acceptance_criteria,
      related_artifacts: artifact.related_artifacts,
    });
  }
  approveAllArtifacts(
    projectId: string,
  ): Observable<{ approved_count: number; total_count: number; artifacts: Artifact[] }> {
    return this.http.post<{ approved_count: number; total_count: number; artifacts: Artifact[] }>(
      `${this.base}/projects/${projectId}/artifacts/approve-all`,
      { confirmed: true },
    );
  }
  listVersions(projectId: string, artifactId: string): Observable<Array<Record<string, unknown>>> {
    return this.http.get<Array<Record<string, unknown>>>(
      `${this.base}/projects/${projectId}/artifacts/${artifactId}/versions`,
    );
  }
  proposeRevision(
    projectId: string,
    artifactId: string,
    instruction: string,
  ): Observable<RevisionProposal> {
    return this.http.post<RevisionProposal>(
      `${this.base}/projects/${projectId}/artifacts/${artifactId}/revision-proposals`,
      { instruction },
    );
  }
  decideRevision(
    projectId: string,
    proposalId: string,
    accept: boolean,
  ): Observable<RevisionProposal> {
    return this.http.post<RevisionProposal>(
      `${this.base}/projects/${projectId}/revision-proposals/${proposalId}/decision`,
      { accept },
    );
  }
  latestValidation(
    projectId: string,
  ): Observable<{ report: ValidationReport | null; created_at: string | null }> {
    return this.http.get<{ report: ValidationReport | null; created_at: string | null }>(
      `${this.base}/projects/${projectId}/validation`,
    );
  }
  exportUrl(projectId: string, format: 'json' | 'docx'): string {
    return `${this.base}/projects/${projectId}/exports/${format}`;
  }
}
