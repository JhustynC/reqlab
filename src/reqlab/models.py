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
    verification_criteria: list[str] | None = None
    ears_pattern: str = "No determinado"
    quality_category: str = ""
    metric: str = ""
    unit: str = ""
    target: str = ""
    verification_method: str = ""
    priority_source: str = "no_definida"
    rationale: str = ""

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
        verification = data.get("verification_criteria", [])
        if isinstance(verification, str):
            verification = [verification]
        priority = cls._normalize_priority(data.get("priority"))
        priority_source = str(data.get("priority_source") or "").strip().lower()
        if priority == "No definida":
            priority_source = "no_definida"
        elif priority_source not in {"corpus", "usuario", "legado"}:
            # Los registros antiguos no conservaban procedencia de prioridad.
            # Se marca explícitamente como legado en vez de fingir que provino
            # del corpus o del usuario.
            priority_source = "legado"
        prefix = {"RF": "RF", "RNF": "RNF", "HU": "HU"}[artifact_type]
        return cls(
            artifact_id=str(data.get("artifact_id") or f"{prefix}-{index:03d}"),
            artifact_type=artifact_type,
            title=str(data.get("title") or "Sin título"),
            description=str(data.get("description") or ""),
            priority=priority,
            source_fragments=[str(item) for item in citations],
            status=str(data.get("status") or "propuesto"),
            acceptance_criteria=criteria,
            related_artifacts=[str(item) for item in relations],
            verification_criteria=[str(item) for item in verification],
            ears_pattern=str(data.get("ears_pattern") or "No determinado"),
            quality_category=str(data.get("quality_category") or ""),
            metric=str(data.get("metric") or ""),
            unit=str(data.get("unit") or ""),
            target=str(data.get("target") or ""),
            verification_method=str(data.get("verification_method") or ""),
            priority_source=priority_source,
            rationale=str(data.get("rationale") or ""),
        )

    @staticmethod
    def _normalize_priority(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        return {
            "alta": "Alta",
            "media": "Media",
            "baja": "Baja",
            "no definida": "No definida",
            "no_definida": "No definida",
        }.get(normalized, "No definida")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
