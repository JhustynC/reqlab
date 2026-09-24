from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


class ArtifactRecord(BaseModel):
    artifact_id: str = ""
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: Literal["Alta", "Media", "Baja"] = "Media"
    source_fragments: list[str] = Field(min_length=1)
    status: Literal["propuesto", "requiere aclaración"] = "propuesto"
    acceptance_criteria: list[str] = Field(default_factory=list)
    related_artifacts: list[str] = Field(default_factory=list)

    @field_validator("priority")
    @classmethod
    def normalize_priority(cls, value: str) -> str:
        normalized = value.strip().capitalize()
        if normalized not in {"Alta", "Media", "Baja"}:
            raise ValueError("La prioridad debe ser Alta, Media o Baja.")
        return normalized

    @field_validator("title", "description")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El texto no puede estar vacío.")
        return value

    @field_validator("source_fragments", "acceptance_criteria", "related_artifacts")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def validate_against_generation_context(self, info: ValidationInfo) -> "ArtifactRecord":
        context: dict[str, Any] = info.context or {}
        valid_citations = set(context.get("valid_citations", []))
        invalid_citations = set(self.source_fragments) - valid_citations if valid_citations else set()
        if invalid_citations:
            raise ValueError(f"Citas inexistentes en el contexto: {sorted(invalid_citations)}")
        valid_relations = set(context.get("valid_relations", []))
        invalid_relations = set(self.related_artifacts) - valid_relations
        if invalid_relations:
            raise ValueError(f"Relaciones inexistentes: {sorted(invalid_relations)}")
        if context.get("artifact_type") == "HU" and not self.acceptance_criteria:
            raise ValueError("Una historia de usuario debe incluir criterios de aceptación.")
        return self


class ArtifactsResponse(BaseModel):
    artifacts: list[ArtifactRecord] = Field(min_length=1)


class RevisionResponse(BaseModel):
    artifact: ArtifactRecord


class EvidenceFinding(BaseModel):
    dimension: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    source_fragments: list[str] = Field(default_factory=list)


class EvidenceUncertainty(BaseModel):
    dimension: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source_fragments: list[str] = Field(default_factory=list)


class DefinitionBatchResponse(BaseModel):
    findings: list[EvidenceFinding] = Field(default_factory=list)
    uncertainties: list[EvidenceUncertainty] = Field(default_factory=list)


class DefinitionProfileRecord(BaseModel):
    dimension: str = Field(min_length=1)
    # El perfil es una sintesis navegable, no una copia de todos los hallazgos.
    # Acotar cada dimension evita que la respuesta completa agote la ventana de
    # salida y quede como JSON truncado.
    value: str = Field(default="", max_length=2000)
    source_fragments: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "missing"]


class DefinitionQuestionRecord(BaseModel):
    dimension: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=400)
    rationale: str = Field(default="", max_length=600)
    source_fragments: list[str] = Field(default_factory=list)


class DefinitionAnalysisResponse(BaseModel):
    profile: list[DefinitionProfileRecord]
    questions: list[DefinitionQuestionRecord] = Field(default_factory=list)
