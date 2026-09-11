from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class GenerationLimits(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rf: int = Field(alias="RF", ge=1, le=30)
    rnf: int = Field(alias="RNF", ge=1, le=30)
    hu: int = Field(alias="HU", ge=1, le=30)

    def as_dict(self) -> dict[str, int]:
        return {"RF": self.rf, "RNF": self.rnf, "HU": self.hu}


class GenerationRequest(BaseModel):
    limits: GenerationLimits | None = None
    # Campo legado para clientes anteriores. Si se envía, aplica el mismo tope
    # a los tres tipos; la nueva interfaz utiliza limits.
    limit_per_type: int | None = Field(default=None, ge=1, le=30)

    @model_validator(mode="after")
    def reject_ambiguous_payload(self) -> "GenerationRequest":
        if self.limits is not None and self.limit_per_type is not None:
            raise ValueError("Envíe limits por tipo o limit_per_type, no ambos.")
        return self

    def resolved_limits(self) -> dict[str, int]:
        if self.limits is not None:
            return self.limits.as_dict()
        fallback = self.limit_per_type if self.limit_per_type is not None else 12
        return {"RF": fallback, "RNF": fallback, "HU": fallback}


class ArtifactUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=8000)
    priority: str = Field(pattern="^(Alta|Media|Baja)$")
    status: str = Field(pattern="^(propuesto|requiere aclaración|aceptado|rechazado)$")
    source_fragments: list[str]
    acceptance_criteria: list[str] = Field(default_factory=list)
    related_artifacts: list[str] | None = None


class RevisionRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=2000)


class RevisionDecision(BaseModel):
    accept: bool
