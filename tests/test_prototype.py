from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from reqlab.corpus import CorpusIngestionAgent
from reqlab.generation import DeepSeekGenerationAgent
from reqlab.models import Artifact
from reqlab.retrieval import TfidfRetrievalAgent
from reqlab.validation import TraceabilityConsistencyAgent


class PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = PROJECT.parent / "caso_estudio_sigsat"
        cls.fragments = CorpusIngestionAgent().load(cls.corpus)

    def test_ingestion_preserves_all_source_fragments(self):
        self.assertEqual(46, len(self.fragments))
        self.assertEqual(46, len({fragment.fragment_id for fragment in self.fragments}))

    def test_retrieval_finds_urgent_rule_context(self):
        result_ids = {fragment.fragment_id for fragment, _ in TfidfRetrievalAgent(self.fragments).retrieve("solicitud urgente plazo dos horas cuatro horas", top_k=8)}
        self.assertIn("SRC-03-F02", result_ids)
        self.assertIn("SRC-06-F01", result_ids)

    def test_validation_reports_invalid_citation(self):
        artifact = Artifact("RF-001", "RF", "Prueba", "El sistema deberá registrar una solicitud.", "Alta", ["SRC-99-F99"])
        report = TraceabilityConsistencyAgent().validate([artifact], self.fragments)
        self.assertIn("RF-001", report["invalid_citations"])

    def test_validation_warns_when_rnf_is_a_functional_capability(self):
        artifact = Artifact("RNF-001", "RNF", "Identificador", "Cada solicitud debe tener un identificador único.", "Alta", ["SRC-03-F01"])
        report = TraceabilityConsistencyAgent().validate([artifact], self.fragments)
        self.assertEqual("RNF-001", report["taxonomy_warnings"][0]["artifact_id"])

    def test_validation_uses_ambiguities_from_the_given_corpus_registry(self):
        artifact = Artifact("RF-001", "RF", "Prueba", "El sistema deberá registrar una solicitud.", "Alta", ["SRC-03-F01"])
        registry = [{"id": "CASE-AMB-01", "topic": "Regla pendiente del caso", "fragment_ids": ["SRC-03-F01"]}]
        report = TraceabilityConsistencyAgent().validate([artifact], self.fragments, registry)
        self.assertEqual("CASE-AMB-01", report["ambiguities_detected"][0]["id"])

    def test_generation_prompt_uses_manifest_metadata_not_a_fixed_domain(self):
        generator = DeepSeekGenerationAgent(
            TfidfRetrievalAgent(self.fragments),
            api_key="test-only",
            system_name="Biblioteca Universitaria",
            domain="gestión de préstamos y colecciones",
        )
        evidence = TfidfRetrievalAgent(self.fragments).retrieve("reglas y usuarios", top_k=2)
        prompt = generator._build_prompt("RF", evidence, 2)
        self.assertIn("Biblioteca Universitaria", prompt)
        self.assertIn("gestión de préstamos y colecciones", prompt)
        self.assertNotIn("SIGSAT", prompt)

    def test_ingestion_accepts_a_different_domain_and_fragment_id_format(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            corpus = Path(temporary_directory)
            (corpus / "corpus_manifest.json").write_text(
                json.dumps(
                    {
                        "corpus_id": "BIB-C01",
                        "version": "1.0",
                        "system_name": "Biblioteca Universitaria",
                        "domain": "préstamo de libros",
                        "fragment_id_regex": "LIB-[A-Z]\\d+",
                        "documents": [{"source_id": "LIB", "file": "politica.md"}],
                    }
                ),
                encoding="utf-8",
            )
            (corpus / "politica.md").write_text("## Política [LIB-A1]\nUna persona puede reservar libros.\n", encoding="utf-8")
            fragments = CorpusIngestionAgent().load(corpus)
        self.assertEqual("LIB-A1", fragments[0].fragment_id)
        self.assertEqual("LIB", fragments[0].source_id)


if __name__ == "__main__":
    unittest.main()
