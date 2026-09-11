export type WorkflowState =
  | 'created'
  | 'sources_ready'
  | 'definition'
  | 'ready_to_generate'
  | 'generating'
  | 'review'
  | 'exported';

export type Phase = 'sources' | 'definition' | 'generation' | 'review' | 'export';
export type ArtifactType = 'RF' | 'RNF' | 'HU';

export type GenerationLimits = Record<ArtifactType, number>;

export interface GenerationBudgetItem {
  minimum: number;
  suggested: number;
  maximum: number;
  signal_fragments: number;
  signal_ratio: number;
}

export interface GenerationRecommendations {
  method_version: string;
  interpretation: string;
  inputs: {
    fragment_count: number;
    document_fragment_count: number;
    definition_fragment_count: number;
    character_count: number;
    evidence_units: number;
    characters_per_evidence_unit: number;
  };
  formula: string;
  limits: Record<ArtifactType, GenerationBudgetItem>;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  domain: string;
  status: WorkflowState;
  definition_confirmed: number;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  source_count: number;
  fragment_count: number;
  artifact_count: number;
}

export interface Source {
  id: string;
  project_id: string;
  source_code: string;
  original_name: string;
  content_type: string;
  source_kind: 'document' | 'email' | 'interview' | 'meeting_notes' | 'conversation' | 'note' | 'other';
  sha256: string;
  status: 'uploaded' | 'processed' | 'indexed' | 'error';
  error_message?: string;
  created_at: string;
}

export interface SourcePreview {
  id: string;
  source_code: string;
  original_name: string;
  content_type: string;
  source_kind: string;
  text: string;
  character_count: number;
  fragment_count: number;
}

export interface FragmentSummary {
  fragment_key: string;
  heading: string;
  position: number;
  source_code: string;
  source_name: string;
}

export interface FragmentDetail extends FragmentSummary {
  text: string;
  metadata: Record<string, unknown>;
}

export interface DefinitionQuestion {
  id: string;
  project_id: string;
  question_key: string;
  question: string;
  rationale: string;
  required: number;
  origin: 'core' | 'dynamic';
  answer: string;
  dimension: string;
  suggested_answer: string;
  evidence: string[];
  confidence: 'high' | 'medium' | 'low' | 'missing' | 'pending' | '';
}

export interface DefinitionAnalysis {
  profile: Array<{
    dimension: string;
    value: string;
    source_fragments: string[];
    confidence: 'high' | 'medium' | 'low' | 'missing';
  }>;
  questions: DefinitionQuestion[];
  coverage: { fragment_count: number; batch_count: number };
}

export interface Artifact {
  id: string;
  project_id: string;
  artifact_key: string;
  artifact_type: ArtifactType;
  title: string;
  description: string;
  priority: 'Alta' | 'Media' | 'Baja';
  source_fragments: string[];
  status: 'propuesto' | 'requiere aclaración' | 'aceptado' | 'rechazado';
  acceptance_criteria: string[];
  related_artifacts: string[];
  validation: {
    status?: 'sin_alertas' | 'requiere_revision';
    warnings?: string[];
  };
  version: number;
  created_at: string;
  updated_at: string;
}

export interface GenerationRun {
  id: string;
  project_id: string;
  phase: string;
  status: 'running' | 'completed' | 'failed';
  agent_id: string;
  error_message?: string;
  parameters: {
    progress?: number;
    message?: string;
    step?: string;
    model?: string;
    retrieval?: string;
    generation_limits?: GenerationLimits;
    generation_budget_method?: string;
    generation_budget_recommendations?: GenerationRecommendations;
    experimental_config?: {
      llm?: { model?: string; base_url?: string };
      embedding?: { model?: string };
      reranker?: { enabled?: boolean; model?: string };
      retrieval?: { method?: string; top_k?: number };
      segmentation?: { chunk_size?: number; overlap?: number };
      prompt_version?: string;
    };
    metrics?: {
      total_latency_ms?: number;
      total_tokens?: number;
      total_attempts?: number;
    };
  };
}

export interface RevisionProposal {
  id: string;
  project_id: string;
  artifact_id: string;
  instruction: string;
  status: 'pending' | 'accepted' | 'rejected' | 'superseded';
  proposal: {
    artifact_id: string;
    artifact_type: ArtifactType;
    title: string;
    description: string;
    priority: 'Alta' | 'Media' | 'Baja';
    source_fragments: string[];
    status: string;
    acceptance_criteria: string[];
    related_artifacts: string[];
  };
}

export interface ValidationReport {
  artifact_count: number;
  artifacts_without_citations: string[];
  invalid_citations: Record<string, string[]>;
  possible_duplicates: Array<{ left: string; right: string; jaccard: number }>;
  cross_type_duplicates: Array<{
    left: string;
    right: string;
    left_type: string;
    right_type: string;
    jaccard: number;
    reason: string;
  }>;
  invalid_relations: Record<string, string[]>;
  user_stories_with_invalid_format: string[];
  user_stories_without_acceptance_criteria: string[];
  taxonomy_warnings: Array<{ artifact_id: string; reason: string }>;
  artifact_validations: Record<string, { status: string; warnings: string[] }>;
  thresholds: { same_type_jaccard: number; cross_type_jaccard: number };
  traceability_status: string;
  quality_status: string;
}
