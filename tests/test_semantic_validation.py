from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from reqlab.models import Artifact, Fragment
from reqlab.semantic_validation import SemanticValidationService
from reqlab.services import ProjectApplicationService
from reqlab.settings import Settings
from reqlab.storage import SQLiteRepository
from reqlab.typesafe_client import TypeSafeDecisionClient, _RetryableTypeSafeError
import reqlab.typesafe_client as typesafe_client_module


class _FakeDecisionClient:
    model = "jev-1.13.0"
    configured = True

    def __init__(self, overall: str = "completo", confidence: float = 0.94):
        self.overall = overall
        self.confidence = confidence
        self.calls: list[dict] = []

    def system_one(self, state, questions, timeout=None):
        del timeout
        self.calls.append({"state": state, "questions": questions})
        answers = {}
        for question_id, question in questions.items():
            labels = list(question["criteria"])
            choice = self.overall if question_id == "overall_support" else "aporta_respaldo"
            probabilities = {label: 0.0 for label in labels}
            probabilities[choice] = 1.0
            answers[question_id] = {
                "type": "choice",
                "choice": choice,
                "probabilities": probabilities,
                "confidence": self.confidence,
            }
        return {"model": self.model, "answers": answers, "usage": {"input_tokens": 75}}

    def get_last_telemetry(self):
        return {
            "latency_ms": 12.5,
            "input_tokens": 75,
            "attempts": 1,
            "effective_model": self.model,
        }


class _MalformedDecisionClient(_FakeDecisionClient):
    def system_one(self, state, questions, timeout=None):
        del state, questions, timeout
        self.calls.append({})
        return {
            "model": self.model,
            "answers": {
                "overall_support": {
                    "type": "choice",
                    "choice": "completo",
                    "probabilities": {"completo": 0.4},
                    "confidence": 1.0,
                }
            },
        }


class _RetryClient(TypeSafeDecisionClient):
    def __init__(self):
        super().__init__(api_key="test", max_attempts=2)
        self.calls = 0

    def _request_once(self, payload, timeout):
        del payload, timeout
        self.calls += 1
        if self.calls == 1:
            raise _RetryableTypeSafeError("temporal")
        return {"model": self.model, "answers": {}, "usage": {"input_tokens": 3}}


def _artifact(**overrides):
    item = {
        "artifact_key": "RF-001",
        "artifact_type": "RF",
        "version": 1,
        "title": "Registro",
        "description": "El sistema permitirá registrar solicitudes.",
        "source_fragments": ["SRC-001-F001"],
        "acceptance_criteria": [],
        "status": "propuesto",
    }
    item.update(overrides)
    return item


class SemanticValidationTests(unittest.TestCase):
    def setUp(self):
        self.fragment = Fragment(
            "SRC-001-F001",
            "SRC-001",
            "proceso.md",
            "Registro",
            "Recepción registra cada solicitud recibida.",
        )

    def test_shadow_evaluation_returns_overall_and_per_link_decisions(self):
        client = _FakeDecisionClient()
        validator = SemanticValidationService(client, enabled=True)
        artifact = _artifact()

        report = validator.evaluate_project("P-1", [artifact], [self.fragment])

        self.assertEqual("completed", report["technical_status"])
        result = report["artifact_results"][0]
        self.assertEqual("completo", result["overall"]["label"])
        self.assertEqual("aporta_respaldo", result["links"][0]["label"])
        self.assertFalse(result["policy"]["requires_review"])
        self.assertEqual(artifact, _artifact(), "La evaluación no debe mutar el artefacto.")
        self.assertIn("ignorarse", client.calls[0]["state"]["evaluation_scope"].lower())

    def test_invalid_citation_skips_remote_call_and_requires_review(self):
        client = _FakeDecisionClient()
        validator = SemanticValidationService(client, enabled=True)

        report = validator.evaluate_project(
            "P-1", [_artifact(source_fragments=["SRC-999-F999"])], [self.fragment]
        )

        result = report["artifact_results"][0]
        self.assertEqual("skipped_invalid_input", result["technical_status"])
        self.assertEqual(["SRC-999-F999"], result["invalid_fragment_ids"])
        self.assertTrue(result["policy"]["requires_review"])
        self.assertEqual([], client.calls)

    def test_low_confidence_can_abstain_without_changing_label(self):
        client = _FakeDecisionClient(confidence=0.6)
        validator = SemanticValidationService(
            client, enabled=True, confidence_threshold=0.8
        )

        result = validator.evaluate_project(
            "P-1", [_artifact()], [self.fragment]
        )["artifact_results"][0]

        self.assertEqual("completo", result["overall"]["label"])
        self.assertTrue(result["policy"]["abstained"])
        self.assertTrue(result["policy"]["requires_review"])

    def test_malformed_contract_is_a_failure_not_a_complete_decision(self):
        client = _MalformedDecisionClient()
        validator = SemanticValidationService(client, enabled=True)

        result = validator.evaluate_project(
            "P-1", [_artifact()], [self.fragment]
        )["artifact_results"][0]

        self.assertEqual("failed", result["technical_status"])
        self.assertIsNone(result["overall"])
        self.assertTrue(result["policy"]["requires_review"])

    def test_snapshot_hash_changes_when_artifact_or_evidence_changes(self):
        validator = SemanticValidationService(_FakeDecisionClient(), enabled=True)
        original = validator.snapshot_hash([_artifact()], [self.fragment])
        edited = validator.snapshot_hash(
            [_artifact(description="Texto editado")], [self.fragment]
        )
        evidence_changed = validator.snapshot_hash(
            [_artifact()],
            [
                Fragment(
                    self.fragment.fragment_id,
                    self.fragment.source_id,
                    self.fragment.source_file,
                    self.fragment.heading,
                    "Evidencia editada",
                )
            ],
        )
        self.assertNotEqual(original, edited)
        self.assertNotEqual(original, evidence_changed)

    def test_repository_keeps_semantic_report_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteRepository(Path(folder) / "test.db")
            project = repository.create_project("Prueba")
            report_id = repository.save_semantic_validation_report(
                project["id"], "abc", {"technical_status": "completed"}
            )
            latest = repository.latest_semantic_validation_report(project["id"])
            deterministic = repository.latest_validation_report(project["id"])

        self.assertEqual(report_id, latest["id"])
        self.assertEqual("abc", latest["input_snapshot_hash"])
        self.assertEqual("completed", latest["report"]["technical_status"])
        self.assertIsNone(deterministic)

    def test_application_service_marks_report_stale_after_artifact_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = SQLiteRepository(root / "test.db")
            project = repository.create_project("Prueba")
            source = repository.add_source(
                project["id"],
                "SRC-001",
                "proceso.md",
                str(root / "proceso.md"),
                "text/markdown",
                "hash-source",
            )
            repository.replace_source_fragments(source, [self.fragment])
            repository.save_artifacts(
                project["id"],
                [
                    Artifact(
                        "RF-001",
                        "RF",
                        "Registro",
                        "El sistema permitirá registrar solicitudes.",
                        "Alta",
                        [self.fragment.fragment_id],
                    )
                ],
            )
            settings = replace(
                Settings.from_environment(),
                data_dir=root,
                semantic_validation_enabled=True,
                typesafe_api_key="test",
            )

            class _GenerationClient:
                model = "unused"

            service = ProjectApplicationService(
                repository,
                object(),
                root,
                _GenerationClient(),
                settings=settings,
                semantic_client=_FakeDecisionClient(),
            )
            service.run_semantic_validation(project["id"])
            self.assertFalse(service.semantic_validation_status(project["id"])["latest"]["stale"])

            current = repository.get_artifact_by_key(project["id"], "RF-001")
            repository.update_artifact(
                current["id"],
                Artifact(
                    "RF-001",
                    "RF",
                    "Registro",
                    "El sistema permitirá registrar y aprobar solicitudes.",
                    "Alta",
                    [self.fragment.fragment_id],
                ),
                "manual_revision",
            )
            status = service.semantic_validation_status(project["id"])

        self.assertTrue(status["latest"]["stale"])
        self.assertEqual("completed", status["latest"]["report"]["technical_status"])

    def test_typesafe_client_retries_only_recoverable_failure(self):
        client = _RetryClient()
        response = client.system_one("state", {"q": {"type": "choice"}})
        self.assertEqual(client.model, response["model"])
        self.assertEqual(2, client.calls)
        self.assertEqual(2, client.get_last_telemetry()["attempts"])

    def test_typesafe_client_uses_openrouter_decisions_endpoint(self):
        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"model":"typesafe/jev-1.13","answers":{}}'

        client = TypeSafeDecisionClient(
            api_key="secret",
            base_url="https://openrouter.ai/api",
            model="typesafe/jev-1.13",
            endpoint_path="/alpha/decisions",
            max_attempts=1,
        )
        with patch.object(typesafe_client_module, "urlopen", return_value=_Response()) as mocked:
            response = client.system_one("state", {"q": {"type": "choice"}})

        request = mocked.call_args.args[0]
        self.assertEqual("https://openrouter.ai/api/alpha/decisions", request.full_url)
        self.assertEqual("Bearer secret", request.get_header("Authorization"))
        self.assertEqual("typesafe/jev-1.13", response["model"])


if __name__ == "__main__":
    unittest.main()
