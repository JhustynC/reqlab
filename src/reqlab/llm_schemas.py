from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ArtifactRecord(BaseModel):
    artifact_id: str = ""
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: str = "Media"
    source_fragments: list[str] = Field(min_length=1)
    status: str = "propuesto"
    acceptance_criteria: list[str] = Field(default_factory=list)

    @field_validator("priority")
    @classmethod
    def normalize_priority(cls, value: str) -> str:
        normalized = value.strip().capitalize()
        return normalized if normalized in {"Alta", "Media", "Baja"} else "Media"


class ArtifactsResponse(BaseModel):
    artifacts: list[ArtifactRecord] = Field(min_length=1)


class RevisionResponse(BaseModel):
    artifact: ArtifactRecord
