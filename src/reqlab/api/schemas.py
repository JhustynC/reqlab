from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=1000)
    domain: str = Field(default="", max_length=240)


class ProjectArchiveUpdate(BaseModel):
    archived: bool


class TextSourceCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    source_type: str = Field(
        default="other",
        pattern="^(email|interview|meeting_notes|conversation|note|other)$",
    )
    text: str = Field(min_length=20, max_length=200000)


class DefinitionAnswer(BaseModel):
    question_key: str = Field(min_length=1, max_length=80)
    answer: str = Field(default="", max_length=5000)


class DefinitionAnswersUpdate(BaseModel):
    answers: list[DefinitionAnswer]


class GenerationRequest(BaseModel):
    limit_per_type: int = Field(default=12, ge=3, le=20)


class ArtifactUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=8000)
    priority: str = Field(pattern="^(Alta|Media|Baja)$")
    status: str = Field(pattern="^(propuesto|requiere aclaración|aceptado|rechazado)$")
    source_fragments: list[str]
    acceptance_criteria: list[str] = Field(default_factory=list)


class RevisionRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=2000)


class RevisionDecision(BaseModel):
    accept: bool
