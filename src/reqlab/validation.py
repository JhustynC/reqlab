from __future__ import annotations

from collections import defaultdict

from .models import Artifact, Fragment
from .retrieval import tokenize


class TraceabilityConsistencyAgent:
    """Verifica trazabilidad mínima, duplicados y ambigüedades conocidas."""

    def __init__(self, duplicate_threshold: float = 0.72, cross_type_duplicate_threshold: float = 0.55):
        self.duplicate_threshold = duplicate_threshold
        self.cross_type_duplicate_threshold = cross_type_duplicate_threshold

    def validate(self, artifacts: list[Artifact], fragments: list[Fragment], ambiguity_registry: list[dict] | None = None) -> dict:
        valid_ids = {fragment.fragment_id for fragment in fragments}
        missing_citations = [artifact.artifact_id for artifact in artifacts if not artifact.source_fragments]
        invalid_citations = {
            artifact.artifact_id: sorted(set(artifact.source_fragments) - valid_ids)
            for artifact in artifacts
            if set(artifact.source_fragments) - valid_ids
        }
        malformed_stories = [
            artifact.artifact_id
            for artifact in artifacts
            if artifact.artifact_type == "HU" and not self._is_user_story(artifact.description)
        ]
        stories_without_criteria = [
            artifact.artifact_id
            for artifact in artifacts
            if artifact.artifact_type == "HU" and not artifact.acceptance_criteria
        ]
        taxonomy_warnings = self._taxonomy_warnings(artifacts)
        invalid_relations = self._invalid_relations(artifacts)
        duplicates = self._duplicates(artifacts, self.duplicate_threshold)
        cross_type_duplicates = self._cross_type_duplicates(
            artifacts, self.cross_type_duplicate_threshold
        )
        traceability_valid = not missing_citations and not invalid_citations
        report = {
            "artifact_count": len(artifacts),
            "artifacts_without_citations": missing_citations,
            "invalid_citations": invalid_citations,
            "possible_duplicates": duplicates,
            "cross_type_duplicates": cross_type_duplicates,
            "invalid_relations": invalid_relations,
            "ambiguities_detected": self._ambiguities(artifacts, ambiguity_registry or []),
            "user_stories_with_invalid_format": malformed_stories,
            "user_stories_without_acceptance_criteria": stories_without_criteria,
            "taxonomy_warnings": taxonomy_warnings,
            "traceability_status": "requiere_revision" if not traceability_valid else "trazabilidad_minima_valida",
            "quality_status": "requiere_revision"
            if (
                malformed_stories
                or stories_without_criteria
                or taxonomy_warnings
                or invalid_relations
                or duplicates
                or cross_type_duplicates
            )
            else "sin_alertas_basicas",
            "thresholds": {
                "same_type_jaccard": self.duplicate_threshold,
                "cross_type_jaccard": self.cross_type_duplicate_threshold,
            },
        }
        report["artifact_validations"] = self._artifact_validations(artifacts, report)
        return report

    @staticmethod
    def _is_user_story(description: str) -> bool:
        lowered = description.strip().lower()
        return lowered.startswith("como ") and ", quiero " in lowered and ", para " in lowered

    @staticmethod
    def _taxonomy_warnings(artifacts: list[Artifact]) -> list[dict]:
        """Señala RNF con redacción típica de una capacidad funcional.

        Es una alerta de revisión, no una reclasificación automática: el juicio del
        experto conserva la última palabra sobre la frontera RF/RNF.
        """
        functional_patterns = (
            "identificador unico",
            "debe permitir",
            "puede consultar",
            "puede modificar",
            "debe registrar",
            "debe asignar",
        )
        warnings: list[dict] = []
        for artifact in artifacts:
            normalized = " ".join(tokenize(artifact.description))
            if artifact.artifact_type == "RNF" and any(pattern in normalized for pattern in functional_patterns):
                warnings.append(
                    {
                        "artifact_id": artifact.artifact_id,
                        "reason": "Un RNF contiene redacción típica de capacidad funcional; revisar su clasificación RF/RNF.",
                    }
                )
        return warnings

    @staticmethod
    def _duplicates(artifacts: list[Artifact], threshold: float = 0.72) -> list[dict]:
        duplicates: list[dict] = []
        for index, left in enumerate(artifacts):
            left_terms = set(tokenize(left.description))
            if not left_terms:
                continue
            for right in artifacts[index + 1 :]:
                if left.artifact_type != right.artifact_type:
                    continue
                right_terms = set(tokenize(right.description))
                union = left_terms | right_terms
                similarity = len(left_terms & right_terms) / len(union) if union else 0.0
                if similarity >= threshold:
                    duplicates.append({"left": left.artifact_id, "right": right.artifact_id, "jaccard": round(similarity, 3)})
        return duplicates

    @staticmethod
    def _cross_type_duplicates(artifacts: list[Artifact], threshold: float = 0.55) -> list[dict]:
        """Detecta artefactos de *tipos distintos* con alta superposición léxica.

        Un umbral más bajo (0.55) que el de duplicados internos porque la coincidencia
        entre, p. ej., un RF y una HU no implica error sino posible redundancia; el
        experto decide si consolidar, reclasificar o mantener ambos con distintos enfoques.
        """
        duplicates: list[dict] = []
        for index, left in enumerate(artifacts):
            left_terms = set(tokenize(left.description))
            if not left_terms:
                continue
            for right in artifacts[index + 1 :]:
                if left.artifact_type == right.artifact_type:
                    continue
                right_terms = set(tokenize(right.description))
                union = left_terms | right_terms
                similarity = len(left_terms & right_terms) / len(union) if union else 0.0
                if similarity >= threshold:
                    duplicates.append({
                        "left": left.artifact_id,
                        "left_type": left.artifact_type,
                        "right": right.artifact_id,
                        "right_type": right.artifact_type,
                        "jaccard": round(similarity, 3),
                        "reason": "Superposición léxica entre tipos distintos; revisar si son complementarios o redundantes.",
                    })
        return duplicates

    @staticmethod
    def _invalid_relations(artifacts: list[Artifact]) -> dict[str, list[str]]:
        known = {artifact.artifact_id for artifact in artifacts}
        return {
            artifact.artifact_id: sorted(set(artifact.related_artifacts or []) - known)
            for artifact in artifacts
            if set(artifact.related_artifacts or []) - known
        }

    @staticmethod
    def _artifact_validations(artifacts: list[Artifact], report: dict) -> dict[str, dict]:
        validations: dict[str, dict] = {}
        duplicate_pairs = report["possible_duplicates"] + report["cross_type_duplicates"]
        for artifact in artifacts:
            key = artifact.artifact_id
            warnings: list[str] = []
            if key in report["artifacts_without_citations"]:
                warnings.append("El artefacto no contiene evidencia vinculada.")
            if key in report["invalid_citations"]:
                warnings.append("El artefacto contiene referencias que no existen en el corpus.")
            if key in report["invalid_relations"]:
                warnings.append("El artefacto contiene relaciones con identificadores inexistentes.")
            if key in report["user_stories_with_invalid_format"]:
                warnings.append("La historia no cumple el patrón Como–quiero–para.")
            if key in report["user_stories_without_acceptance_criteria"]:
                warnings.append("La historia no incluye criterios de aceptación.")
            warnings.extend(
                item["reason"] for item in report["taxonomy_warnings"] if item["artifact_id"] == key
            )
            for pair in duplicate_pairs:
                if key in {pair["left"], pair["right"]}:
                    other = pair["right"] if pair["left"] == key else pair["left"]
                    warnings.append(f"Revisar posible solapamiento con {other}.")
            validations[key] = {
                "status": "requiere_revision" if warnings else "sin_alertas",
                "warnings": list(dict.fromkeys(warnings)),
            }
        return validations

    @staticmethod
    def _ambiguities(artifacts: list[Artifact], ambiguity_registry: list[dict]) -> list[dict]:
        found: dict[str, list[str]] = defaultdict(list)
        for artifact in artifacts:
            cited = set(artifact.source_fragments)
            for definition in ambiguity_registry:
                ambiguity_id = str(definition.get("id", "sin_id"))
                fragment_ids = set(definition.get("fragment_ids", []))
                if cited & fragment_ids:
                    found[ambiguity_id].append(artifact.artifact_id)
        return [
            {
                "id": ambiguity_id,
                "topic": next((item.get("topic", "Sin tema") for item in ambiguity_registry if item.get("id") == ambiguity_id), "Sin tema"),
                "artifacts": ids,
            }
            for ambiguity_id, ids in found.items()
        ]

    @staticmethod
    def traceability_markdown(artifacts: list[Artifact]) -> str:
        rows = ["# Matriz de trazabilidad generada", "", "| Artefacto | Tipo | Procedencia a nivel de fragmento | Estado |", "|---|---|---|---|"]
        for artifact in artifacts:
            citations = ", ".join(artifact.source_fragments) or "Sin cita"
            rows.append(f"| {artifact.artifact_id} | {artifact.artifact_type} | {citations} | {artifact.status} |")
        return "\n".join(rows) + "\n"
