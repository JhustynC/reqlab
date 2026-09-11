from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Fragment:
    """Unidad recuperable identificada dentro de una fuente del corpus."""

    fragment_id: str
    source_id: str
    source_file: str
    heading: str
    text: str


@dataclass
class Artifact:
    """Artefacto generado cuya procedencia debe poder verificarse."""

    artifact_id: str
    artifact_type: str
    title: str
    description: str
    priority: str
    source_fragments: list[str]
    status: str = "propuesto"
    acceptance_criteria: list[str] | None = None
    related_artifacts: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], artifact_type: str, index: int) -> "Artifact":
        citations = data.get("source_fragments", [])
        if isinstance(citations, str):
            citations = [citations]
        criteria = data.get("acceptance_criteria")
        if isinstance(criteria, str):
            criteria = [criteria]
        relations = data.get("related_artifacts", [])
        if isinstance(relations, str):
            relations = [relations]
        prefix = {"RF": "RF", "RNF": "RNF", "HU": "HU"}[artifact_type]
        return cls(
            artifact_id=str(data.get("artifact_id") or f"{prefix}-{index:03d}"),
            artifact_type=artifact_type,
            title=str(data.get("title") or "Sin título"),
            description=str(data.get("description") or ""),
            priority=str(data.get("priority") or "Media"),
            source_fragments=[str(item) for item in citations],
            status=str(data.get("status") or "propuesto"),
            acceptance_criteria=criteria,
            related_artifacts=[str(item) for item in relations],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
