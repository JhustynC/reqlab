from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from reqlab.api.schemas import GenerationRequest
from reqlab.generation_budget import (
    ABSOLUTE_MAXIMUM,
    normalize_generation_limits,
    recommend_generation_budgets,
    validate_generation_limits,
)
from reqlab.models import Fragment


def fragment(index: int, text: str, source_id: str = "SRC-001") -> Fragment:
    return Fragment(f"{source_id}-F{index:03d}", source_id, "source.txt", "Section", text)


class GenerationBudgetTests(unittest.TestCase):
    def test_recommendation_scales_with_evidence_volume(self):
        small = recommend_generation_budgets([fragment(1, "El operador registra una solicitud.")])
        large = recommend_generation_budgets(
            [fragment(index, "El operador registra, consulta y actualiza solicitudes. " * 15) for index in range(1, 21)]
        )
        self.assertGreater(large["limits"]["RF"]["suggested"], small["limits"]["RF"]["suggested"])
        self.assertLessEqual(large["limits"]["RF"]["maximum"], ABSOLUTE_MAXIMUM)

    def test_type_signals_adjust_each_budget_without_becoming_a_quota(self):
        result = recommend_generation_budgets(
            [
                fragment(1, "El sistema debe registrar, consultar, actualizar, asignar y notificar solicitudes."),
                fragment(2, "El operador gestiona el estado y el flujo de cada solicitud."),
            ]
        )
        self.assertGreater(result["limits"]["RF"]["signal_fragments"], result["limits"]["RNF"]["signal_fragments"])
        self.assertIn("no estimación", result["interpretation"])

    def test_limits_require_all_three_types_and_safe_bounds(self):
        self.assertEqual(
            {"RF": 5, "RNF": 4, "HU": 6},
            normalize_generation_limits({"RF": 5, "RNF": 4, "HU": 6}),
        )
        with self.assertRaises(ValueError):
            normalize_generation_limits({"RF": 5, "RNF": 4})
        with self.assertRaises(ValueError):
            normalize_generation_limits({"RF": 31, "RNF": 4, "HU": 6})

    def test_api_accepts_per_type_limits_and_preserves_legacy_payload(self):
        self.assertEqual(
            {"RF": 8, "RNF": 5, "HU": 7},
            GenerationRequest(limits={"RF": 8, "RNF": 5, "HU": 7}).resolved_limits(),
        )
        self.assertEqual(
            {"RF": 6, "RNF": 6, "HU": 6},
            GenerationRequest(limit_per_type=6).resolved_limits(),
        )
        with self.assertRaises(ValidationError):
            GenerationRequest(limits={"RF": 8, "RNF": 5, "HU": 7}, limit_per_type=6)

    def test_selected_limits_must_respect_the_corpus_specific_maximum(self):
        recommendations = recommend_generation_budgets(
            [fragment(1, "El operador registra una solicitud y consulta su estado.")]
        )
        valid = {
            artifact_type: item["suggested"]
            for artifact_type, item in recommendations["limits"].items()
        }
        self.assertEqual(valid, validate_generation_limits(valid, recommendations))
        invalid = dict(valid)
        invalid["RF"] = recommendations["limits"]["RF"]["maximum"] + 1
        with self.assertRaises(ValueError):
            validate_generation_limits(invalid, recommendations)

if __name__ == "__main__":
    unittest.main()
