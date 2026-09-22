from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel, Field


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from reqlab.agents import CONTRACTS, SpecializedGenerationAgent
from reqlab.documents import TextSegmentationService
from reqlab.llm import OpenAICompatibleClient
from reqlab.models import Fragment
from reqlab.models import Artifact
from reqlab.validation import TraceabilityConsistencyAgent
from reqlab.vector_store import SentenceTransformerEmbeddingProvider


class _FakeEncoder:
    def __init__(self):
        self.inputs: list[str] = []

    def encode(self, texts, **_kwargs):
        self.inputs.extend(texts)

        class Vector(list):
            def tolist(self):
                return list(self)

        return [Vector([1.0, 0.0]) for _ in texts]


class _ValidatedPayload(BaseModel):
    values: list[str] = Field(min_length=1)


class _RetryClient(OpenAICompatibleClient):
    def __init__(self):
        super().__init__(api_key="test", max_retries=2)
        self.calls = 0

    def complete_json(self, *args, **kwargs):
        del args, kwargs
        self.calls += 1
        self._set_telemetry({"latency_ms": 10, "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "attempts": 1})
        return {"values": [] if self.calls == 1 else ["ok"]}


class _AlwaysInvalidClient(OpenAICompatibleClient):
    def __init__(self):
        super().__init__(api_key="test", max_retries=1)

    def complete_json(self, *args, **kwargs):
        del args, kwargs
        self._set_telemetry({"latency_ms": 1, "attempts": 1})
        return {"values": []}


class _FakeHttpResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({
            "model": "deepseek-flash",
            "system_fingerprint": "fp_test",
            "choices": [{
                "message": {"content": '{"values":["ok"]}'},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 5,
                "total_tokens": 25,
                "prompt_cache_hit_tokens": 4,
                "prompt_cache_miss_tokens": 16,
                "completion_tokens_details": {"reasoning_tokens": 0},
            },
        }).encode("utf-8")


class _Retriever:
    def __init__(self):
        self.top_k = 0
        self.fragment = Fragment("SRC-001-F001", "SRC-001", "source.txt", "Source", "Evidence")

    def retrieve(self, query, top_k=12):
        del query
        self.top_k = top_k
        return [(self.fragment, 0.9)]


class _FailingValidatedClient:
    model = "fake"
    configured = True

    def __init__(self):
        self.fallback_calls = 0

    def complete_json_validated(self, **kwargs):
        del kwargs
        raise RuntimeError("validation failed")

    def complete_json(self, **kwargs):
        del kwargs
        self.fallback_calls += 1
        return {"artifacts": []}


class RagImprovementTests(unittest.TestCase):
    def test_deepseek_flash_request_disables_thinking_and_records_served_version(self):
        client = OpenAICompatibleClient(
            api_key="test",
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            thinking_enabled=False,
            max_tokens=12000,
        )
        with patch("reqlab.llm.urlopen", return_value=_FakeHttpResponse()) as mocked:
            response = client.complete_json("Devuelve JSON", "Entrada")

        request = mocked.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        telemetry = client.get_last_telemetry()
        self.assertEqual({"values": ["ok"]}, response)
        self.assertEqual("deepseek-flash", body["model"])
        self.assertEqual({"type": "disabled"}, body["thinking"])
        self.assertEqual(12000, body["max_tokens"])
        self.assertEqual("deepseek-flash", telemetry["served_model"])
        self.assertEqual("fp_test", telemetry["system_fingerprint"])
        self.assertEqual("disabled", telemetry["thinking_mode"])

    def test_e5_query_uses_only_query_prefix(self):
        provider = SentenceTransformerEmbeddingProvider("test", "query: ", "passage: ")
        encoder = _FakeEncoder()
        provider._model = encoder
        provider.embed_query("estado de solicitud")
        provider.embed_documents(["contenido de fuente"])
        self.assertEqual(["query: estado de solicitud", "passage: contenido de fuente"], encoder.inputs)

    def test_validated_retry_telemetry_counts_each_attempt_once(self):
        client = _RetryClient()
        response = client.complete_json_validated("system", "user", _ValidatedPayload)
        self.assertEqual(["ok"], response.values)
        self.assertEqual(2, client.get_last_telemetry()["attempts"])
        self.assertEqual(20, client.get_last_telemetry()["latency_ms"])
        self.assertEqual(10, client.get_last_telemetry()["total_tokens"])

    def test_final_validation_failure_exposes_a_safe_specific_reason(self):
        client = _AlwaysInvalidClient()
        with self.assertRaisesRegex(RuntimeError, "values"):
            client.complete_json_validated("system", "user", _ValidatedPayload)
        self.assertIn("values", client.get_last_telemetry()["last_error"])

    def test_generation_does_not_bypass_failed_validation(self):
        client = _FailingValidatedClient()
        agent = SpecializedGenerationAgent(CONTRACTS["RF"], _Retriever(), client, "Project", "Domain")
        with self.assertRaisesRegex(RuntimeError, "validation failed"):
            agent.generate(limit=3)
        self.assertEqual(0, client.fallback_calls)

    def test_generation_honors_configured_top_k(self):
        retriever = _Retriever()

        class LegacyClient:
            model = "fake"
            configured = True

            def complete_json(self, **_kwargs):
                return {"artifacts": [{
                    "title": "Registro",
                    "description": "El sistema deberá registrar solicitudes.",
                    "priority": "Alta",
                    "source_fragments": ["SRC-001-F001"],
                }]}

        SpecializedGenerationAgent(
            CONTRACTS["RF"], retriever, LegacyClient(), "Project", "Domain", retrieval_top_k=7
        ).generate(limit=3)
        self.assertEqual(7, retriever.top_k)

    def test_generation_prompt_uses_real_allowed_identifiers(self):
        retriever = _Retriever()

        class CapturingClient:
            model = "fake"
            configured = True
            prompt = ""

            def complete_json(self, **kwargs):
                self.prompt = kwargs["user_prompt"]
                return {"artifacts": [{
                    "title": "Registro",
                    "description": "El sistema deberá registrar solicitudes.",
                    "source_fragments": ["SRC-001-F001"],
                    "related_artifacts": [],
                }]}

        client = CapturingClient()
        SpecializedGenerationAgent(CONTRACTS["RF"], retriever, client, "Project", "Domain").generate(limit=3)
        self.assertIn('"source_fragments": ["SRC-001-F001"]', client.prompt)
        self.assertIn("Si la lista está vacía, usa related_artifacts: []", client.prompt)
        self.assertNotIn("identificador exacto de un fragmento", client.prompt)

    def test_email_segmentation_uses_email_structure(self):
        fragments = TextSegmentationService(chunk_size=300, overlap=20).segment(
            "De: cliente@example.com\nPara: equipo@example.com\nAsunto: Solicitud\n\nNecesitamos registrar pedidos y consultar su estado.",
            "SRC-001",
            "correo.txt",
            source_kind="email",
        )
        self.assertTrue(fragments)
        self.assertTrue(any(fragment.heading.startswith("De:") for fragment in fragments))

    def test_relation_validation_and_thresholds_are_reported(self):
        fragments = [Fragment("SRC-001-F001", "SRC-001", "source.txt", "Source", "Evidence")]
        artifacts = [
            Artifact("RF-001", "RF", "Registro", "El sistema deberá registrar solicitudes.", "Alta", ["SRC-001-F001"]),
            Artifact(
                "HU-001", "HU", "Registro", "Como operador, quiero registrar solicitudes, para dar seguimiento.",
                "Alta", ["SRC-001-F001"], acceptance_criteria=["La solicitud queda registrada."],
                related_artifacts=["RF-999"],
            ),
        ]
        report = TraceabilityConsistencyAgent(0.8, 0.4).validate(artifacts, fragments)
        self.assertEqual(["RF-999"], report["invalid_relations"]["HU-001"])
        self.assertEqual(0.4, report["thresholds"]["cross_type_jaccard"])
        self.assertEqual("requiere_revision", report["artifact_validations"]["HU-001"]["status"])


if __name__ == "__main__":
    unittest.main()
