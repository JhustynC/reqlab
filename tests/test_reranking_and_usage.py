from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from reqlab.agents import ProjectDefinitionAgent
from reqlab.jev_reranker import JevReranker
from reqlab.models import Fragment
from reqlab.services import ProjectApplicationService
from reqlab.settings import Settings
from reqlab.storage import SQLiteRepository
from reqlab.vector_store import CrossEncoderReranker


class _Payload(BaseModel):
    value: str


class _MeasuredClient:
    def __init__(self):
        self.calls = 0

    def complete_json(self, **_kwargs):
        self.calls += 1
        return {"value": "ok"}

    def get_last_telemetry(self):
        return {"total_tokens": 7, "prompt_tokens": 5, "completion_tokens": 2, "attempts": 1}


class RerankingAndUsageTests(unittest.TestCase):
    def test_jev_reranks_candidates_and_reports_provider_tokens(self):
        first = Fragment("SRC-001-F001", "SRC-001", "source.txt", "A", "texto general")
        second = Fragment("SRC-001-F002", "SRC-001", "source.txt", "B", "regla concreta")
        client = JevReranker("test-key", batch_size=8)

        def response(payload):
            self.assertEqual("typesafe/jev-1.13", payload["model"])
            self.assertEqual([first.fragment_id, second.fragment_id], [p["id"] for p in payload["state"]["passages"]])
            return {
                "answers": {
                    "relevant_0": {"type": "noul", "noul": 0.3},
                    "evidence_0": {"type": "noul", "noul": 0.2},
                    "relevant_1": {"type": "noul", "noul": 0.9},
                    "evidence_1": {"type": "noul", "noul": 0.8},
                },
                "usage": {"input_tokens": 100, "output_tokens": 8},
            }

        with patch.object(client, "_decide", side_effect=response):
            ranked = client.rerank("reglas de registro", [(first, 0.9), (second, 0.7)], 2)
        self.assertEqual([second.fragment_id, first.fragment_id], [item.fragment_id for item, _ in ranked])
        self.assertEqual(108, client.get_last_telemetry()["total_tokens"])

    def test_reranking_preference_survives_repository_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            repository = SQLiteRepository(path)
            repository.save_reranking_preference(True, "jev")
            self.assertEqual(
                {"enabled": True, "provider": "jev"},
                SQLiteRepository(path).get_reranking_preference(),
            )

    def test_saved_preference_changes_the_next_retriever(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteRepository(Path(folder) / "test.db")
            settings = replace(Settings.from_environment(), typesafe_api_key="test", reranker_enabled=False)
            service = ProjectApplicationService(
                repository, object(), folder, _MeasuredClient(), settings=settings
            )
            self.assertIsNone(service._retriever("project", []).reranker)
            repository.save_reranking_preference(True, "local")
            self.assertIsInstance(service._retriever("project", []).reranker, CrossEncoderReranker)
            repository.save_reranking_preference(True, "jev")
            self.assertIsInstance(service._retriever("project", []).reranker, JevReranker)
            repository.save_reranking_preference(False, "jev")
            self.assertIsNone(service._retriever("project", []).reranker)

    def test_project_usage_counts_each_generation_once(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteRepository(Path(folder) / "test.db")
            project = repository.create_project("Prueba")
            definition = repository.start_run(project["id"], "definition", "definition.main")
            repository.finish_run(definition, "completed", metrics={"total_tokens": 40})
            child = repository.start_run(project["id"], "generation", "agent.rf")
            repository.finish_run(child, "completed", metrics={"total_tokens": 20})
            parent = repository.start_run(project["id"], "generation", "orchestrator.main")
            repository.finish_run(parent, "completed", metrics={"total_tokens": 20, "jev_tokens": 5})
            usage = repository.project_token_usage(project["id"])
            self.assertEqual(65, usage["total_tokens"])
            self.assertEqual({"sources": 0, "definition": 40, "generation": 20,
                              "revision": 0, "semantic_validation": 0, "jev": 5}, usage["by_phase"])

    def test_project_usage_includes_revisions_and_semantic_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteRepository(Path(folder) / "test.db")
            project = repository.create_project("Prueba")
            revision = repository.start_run(project["id"], "revision", "revision.main")
            repository.finish_run(revision, "completed", metrics={"total_tokens": 12, "jev": {"total_tokens": 3}})
            validation = repository.start_run(project["id"], "semantic_validation", "semantic.validator")
            repository.finish_run(validation, "completed", metrics={"total_tokens": 9})
            usage = repository.project_token_usage(project["id"])
            self.assertEqual(24, usage["total_tokens"])
            self.assertEqual(12, usage["by_phase"]["revision"])
            self.assertEqual(9, usage["by_phase"]["semantic_validation"])
            self.assertEqual(3, usage["by_phase"]["jev"])

    def test_failed_generation_counts_recorded_child_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteRepository(Path(folder) / "test.db")
            project = repository.create_project("Prueba")
            parent = repository.start_run(project["id"], "generation", "orchestrator.main")
            child = repository.start_run(
                project["id"], "generation", "agent.rf", {"parent_run_id": parent}
            )
            repository.finish_run(child, "failed", metrics={"total_tokens": 12, "jev": {"total_tokens": 3}})
            repository.finish_run(parent, "failed")
            usage = repository.project_token_usage(project["id"])
            self.assertEqual(15, usage["total_tokens"])
            self.assertEqual(0, usage["unreported_runs"])

    def test_definition_telemetry_sums_every_call(self):
        agent = ProjectDefinitionAgent(_MeasuredClient())
        agent._telemetry.set({"total_tokens": 0, "calls": 0})
        agent._complete_validated(_Payload, system_prompt="s", user_prompt="u")
        agent._complete_validated(_Payload, system_prompt="s", user_prompt="u")
        self.assertEqual(14, agent.get_last_telemetry()["total_tokens"])
        self.assertEqual(2, agent.get_last_telemetry()["calls"])


if __name__ == "__main__":
    unittest.main()
