from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


OverallSupport = Literal["completo", "parcial", "ausente", "contradictorio", "indeterminado"]
LinkSupport = Literal[
    "aporta_respaldo", "solo_contexto", "irrelevante", "contradice", "indeterminado"
]


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float]
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_distribution(self) -> "ChoiceAnswer":
        if self.choice not in self.probabilities:
            raise ValueError("La opción elegida no aparece en probabilities.")
        if any(value < 0 or value > 1 for value in self.probabilities.values()):
            raise ValueError("Las probabilidades deben estar entre 0 y 1.")
        total = sum(self.probabilities.values())
        if abs(total - 1.0) > 0.02:
            raise ValueError("Las probabilidades deben sumar aproximadamente 1.")
        return self


class SystemOneResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    answers: dict[str, ChoiceAnswer]
    usage: dict[str, Any] = Field(default_factory=dict)
