from __future__ import annotations

import math
import re
import unicodedata
from typing import Iterable

from .models import Fragment


METHOD_VERSION = "evidence-budget-v1"
ABSOLUTE_MINIMUM = 1
ABSOLUTE_MAXIMUM = 30
SUGGESTED_MAXIMUM = 24
CHARACTERS_PER_EVIDENCE_UNIT = 900


# Son indicios lingüísticos del tipo de artefacto, no vocabulario de un dominio
# concreto. Solo ajustan un presupuesto operativo; no clasifican requisitos.
TYPE_SIGNALS: dict[str, tuple[str, ...]] = {
    "RF": (
        "registrar", "consultar", "crear", "actualizar", "modificar", "eliminar",
        "asignar", "gestionar", "notificar", "generar", "visualizar", "permitir",
        "proceso", "flujo", "estado", "solicitud", "acción", "función",
    ),
    "RNF": (
        "seguridad", "privacidad", "rendimiento", "disponibilidad", "autenticación",
        "cifrado", "retención", "usabilidad", "accesibilidad", "auditoría", "respaldo",
        "tiempo de respuesta", "segundos", "minutos", "horas", "restricción", "normativa",
    ),
    "HU": (
        "usuario", "actor", "rol", "residente", "cliente", "administrador", "operador",
        "técnico", "proveedor", "responsable", "necesita", "quiere", "beneficio",
        "objetivo", "escenario", "interacción",
    ),
}


def recommend_generation_budgets(fragments: Iterable[Fragment]) -> dict:
    """Calcula topes operativos trazables; no estima el número real de requisitos."""
    items = list(fragments)
    if not items:
        raise ValueError("El proyecto no contiene fragmentos para dimensionar la generación.")

    normalized = [_normalize(fragment.text) for fragment in items]
    character_count = sum(len(fragment.text.strip()) for fragment in items)
    volume_units = sum(
        max(1, math.ceil(len(fragment.text.strip()) / CHARACTERS_PER_EVIDENCE_UNIT))
        for fragment in items
    )
    base = 2 * math.sqrt(volume_units)
    limits: dict[str, dict[str, int | float]] = {}

    for artifact_type, signals in TYPE_SIGNALS.items():
        signal_fragments = sum(
            1 for text in normalized if any(_normalize(signal) in text for signal in signals)
        )
        signal_ratio = signal_fragments / len(items)
        # El factor conserva una contribución de volumen aunque no haya coincidencia
        # léxica y limita cuánto pueden alterar el resultado los indicios del tipo.
        type_factor = 0.75 + (0.50 * signal_ratio)
        suggested = _clamp(round(base * type_factor), ABSOLUTE_MINIMUM, SUGGESTED_MAXIMUM)
        maximum = _clamp(
            max(suggested + 2, math.ceil(suggested * 1.5)),
            3,
            ABSOLUTE_MAXIMUM,
        )
        limits[artifact_type] = {
            "minimum": ABSOLUTE_MINIMUM,
            "suggested": suggested,
            "maximum": maximum,
            "signal_fragments": signal_fragments,
            "signal_ratio": round(signal_ratio, 4),
        }

    return {
        "method_version": METHOD_VERSION,
        "interpretation": (
            "Presupuesto máximo de salida, no estimación del número verdadero de requisitos. "
            "El agente puede devolver menos artefactos cuando la evidencia no sustenta más."
        ),
        "inputs": {
            "fragment_count": len(items),
            "document_fragment_count": sum(1 for fragment in items if fragment.source_id != "USR-DEF"),
            "definition_fragment_count": sum(1 for fragment in items if fragment.source_id == "USR-DEF"),
            "character_count": character_count,
            "evidence_units": volume_units,
            "characters_per_evidence_unit": CHARACTERS_PER_EVIDENCE_UNIT,
        },
        "formula": (
            "suggested=round(2*sqrt(evidence_units)*(0.75+0.50*signal_ratio)); "
            "maximum=min(30,max(suggested+2,ceil(1.5*suggested)))"
        ),
        "limits": limits,
    }


def normalize_generation_limits(
    limits_by_type: dict[str, int] | None = None,
    fallback: int = 12,
) -> dict[str, int]:
    source = limits_by_type or {artifact_type: fallback for artifact_type in TYPE_SIGNALS}
    missing = set(TYPE_SIGNALS) - set(source)
    unknown = set(source) - set(TYPE_SIGNALS)
    if missing or unknown:
        raise ValueError(
            f"Los límites deben contener exactamente RF, RNF y HU. Faltantes: {sorted(missing)}; "
            f"desconocidos: {sorted(unknown)}."
        )
    normalized: dict[str, int] = {}
    for artifact_type in TYPE_SIGNALS:
        value = source[artifact_type]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"El límite de {artifact_type} debe ser un entero.")
        if not ABSOLUTE_MINIMUM <= value <= ABSOLUTE_MAXIMUM:
            raise ValueError(
                f"El límite de {artifact_type} debe estar entre {ABSOLUTE_MINIMUM} y {ABSOLUTE_MAXIMUM}."
            )
        normalized[artifact_type] = value
    return normalized


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    plain = "".join(character for character in decomposed if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", plain)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
