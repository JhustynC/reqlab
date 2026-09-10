from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from reqlab.agents import ProjectDefinitionAgent
from reqlab.models import Fragment
from reqlab.services import ProjectApplicationService, project_export_payload
from reqlab.storage import SQLiteRepository


class FakeVectorStore:
    def __init__(self):
        self.fragments = {}

    def index(self, project_id, fragments):
        self.fragments[project_id] = list(fragments)

    def retrieve(self, project_id, query, top_k=12):
        del query
        return [(fragment, 0.9) for fragment in self.fragments.get(project_id, [])[:top_k]]

    def delete_project(self, project_id):
        self.fragments.pop(project_id, None)


class FakeDeepSeekClient:
    model = "fake-deepseek"
    configured = True

    def __init__(self):
        self.prompts = []

    def complete_json(self, system_prompt, user_prompt, temperature=0.1, timeout=120):
        del system_prompt, temperature, timeout
        self.prompts.append(user_prompt)
        if "Tarea exclusiva del agente" in user_prompt:
            if "historias de usuario" in user_prompt.lower():
                description = "Como operador, quiero registrar solicitudes, para mantener su seguimiento"
                criteria = ["La solicitud queda registrada con un identificador."]
            elif "atributos de calidad" in user_prompt.lower():
                description = "El sistema deberá conservar el registro de cada solicitud según la política declarada."
                criteria = []
            else:
                description = "El sistema deberá permitir registrar una solicitud."
                criteria = []
            return {
                "artifacts": [
                    {
                        "title": "Registro de solicitudes",
                        "description": description,
                        "priority": "Alta",
                        "source_fragments": ["SRC-001-F001"],
                        "status": "propuesto",
                        "acceptance_criteria": criteria,
                    }
                ]
            }
        if "Extrae hallazgos" in user_prompt:
            return {
                "findings": [{"dimension": "project_goal", "statement": "Centralizar solicitudes.", "source_fragments": ["SRC-001-F001"]}],
                "uncertainties": [{"dimension": "out_of_scope", "description": "No se indican exclusiones.", "source_fragments": []}],
            }
        if "Fusiona resúmenes" in user_prompt:
            return {"findings": [], "uncertainties": []}
        if "Construye un perfil provisional" in user_prompt:
            values = {
                "project_goal": ("Centralizar la atención de solicitudes.", "high"),
                "problem": ("El seguimiento actual es disperso.", "medium"),
                "actors": ("Operador y responsable de atención.", "high"),
                "scope": ("Registrar y dar seguimiento a solicitudes.", "high"),
                "out_of_scope": ("", "missing"),
                "business_and_legal_constraints": ("Conservar el estado y el responsable.", "medium"),
                "quality_expectations": ("", "missing"),
                "known_conflicts": ("No se detectaron contradicciones explícitas.", "high"),
            }
            return {
                "profile": [
                    {"dimension": dimension, "value": value, "source_fragments": ["SRC-001-F001"] if value else [], "confidence": confidence}
                    for dimension, (value, confidence) in values.items()
                ],
                "questions": [
                    {"dimension": "out_of_scope", "question": "¿Qué queda fuera del alcance?", "rationale": "El corpus no incluye exclusiones.", "source_fragments": []},
                    {"dimension": "quality_expectations", "question": "¿Qué expectativas de calidad deben verificarse?", "rationale": "No hay atributos de calidad explícitos.", "source_fragments": []},
                ],
            }
        return {"artifact": {}}


class WebWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.repository = SQLiteRepository(root / "requirements.db")
        self.vector_store = FakeVectorStore()
        self.client = FakeDeepSeekClient()
        self.service = ProjectApplicationService(
            self.repository,
            self.vector_store,
            root,
            self.client,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_project_ingestion_and_definition_are_persistent(self):
        project = self.service.create_project("Mesa de ayuda", "Gestiona solicitudes", "soporte")
        source = self.service.ingest(
            project["id"],
            "descripcion.txt",
            b"El operador registra solicitudes de soporte.\n\nCada solicitud conserva su estado y responsable.",
            "text/plain",
        )
        self.assertEqual("indexed", source["status"])
        self.assertGreater(self.repository.count_fragments(project["id"]), 0)

        self.service.analyze_definition(project["id"])
        questions = self.repository.list_questions(project["id"])
        self.assertTrue(all(not item["required"] for item in questions if item["origin"] == "core"))
        self.assertEqual(2, len([item for item in questions if item["origin"] == "dynamic"]))
        for question in questions:
            if question["required"]:
                self.repository.save_answer(project["id"], question["question_key"], "Respuesta controlada para la prueba.")
        profile = self.service.confirm_definition(project["id"])

        self.assertTrue(self.repository.get_project(project["id"])["definition_confirmed"])
        self.assertEqual("Centralizar la atención de solicitudes.", profile["project_goal"])
        self.assertTrue(any(item.fragment_id.startswith("USR-DEF-") for item in self.repository.list_fragments(project["id"])))

    def test_complete_generation_flow_saves_three_agent_outputs(self):
        project = self.service.create_project("Mesa de ayuda", domain="soporte")
        self.service.ingest(
            project["id"],
            "fuente.txt",
            b"El operador registra solicitudes. Cada solicitud debe conservar su identificador y estado.",
            "text/plain",
        )
        self.service.analyze_definition(project["id"])
        for question in self.repository.list_questions(project["id"]):
            if question["required"]:
                self.repository.save_answer(project["id"], question["question_key"], "No aplica en este caso de prueba.")
        self.service.confirm_definition(project["id"])

        result = self.service.generate_artifacts(project["id"], limit_per_type=3)
        saved = self.repository.list_artifacts(project["id"])

        self.assertEqual(3, len(result["artifacts"]))
        self.assertEqual({"RF", "RNF", "HU"}, {item["artifact_type"] for item in saved})
        self.assertEqual("review", self.repository.get_project(project["id"])["status"])
        self.assertEqual(3, project_export_payload(self.repository, project["id"])["validation"]["artifact_count"])

    def test_source_preview_and_deletion_invalidate_derived_content(self):
        project = self.service.create_project("Mesa de ayuda", domain="soporte")
        source = self.service.ingest(
            project["id"],
            "correo.txt",
            b"El operador recibe un correo informal. Luego registra y asigna la solicitud al tecnico disponible.",
            "text/plain",
        )
        preview = self.service.preview_source(project["id"], source["id"])
        self.assertIn("correo informal", preview["text"])
        self.assertGreater(preview["fragment_count"], 0)

        self.service.analyze_definition(project["id"])
        for question in self.repository.list_questions(project["id"]):
            if question["required"]:
                self.repository.save_answer(project["id"], question["question_key"], "Respuesta confirmada.")
        self.service.confirm_definition(project["id"])
        self.service.generate_artifacts(project["id"], limit_per_type=3)
        stored_path = Path(source["stored_path"])

        self.service.delete_source(project["id"], source["id"])

        self.assertFalse(stored_path.exists())
        self.assertEqual([], self.repository.list_sources(project["id"]))
        self.assertEqual([], self.repository.list_artifacts(project["id"]))
        self.assertEqual("created", self.repository.get_project(project["id"])["status"])
        self.assertFalse(self.repository.get_project(project["id"])["definition_confirmed"])

    def test_projects_can_be_archived_restored_and_deleted(self):
        project = self.service.create_project("Proyecto temporal")
        self.service.archive_project(project["id"], True)
        self.assertEqual([], self.repository.list_projects())
        self.assertEqual(project["id"], self.repository.list_projects(archived=True)[0]["id"])

        self.service.archive_project(project["id"], False)
        self.assertEqual(project["id"], self.repository.list_projects()[0]["id"])
        self.assertEqual([], self.repository.list_projects(archived=True))

        self.service.delete_project(project["id"])
        with self.assertRaises(KeyError):
            self.repository.get_project(project["id"])

    def test_pasted_text_is_a_traceable_source_without_a_template(self):
        project = self.service.create_project("Proyecto abierto")
        source = self.service.ingest_text(
            project["id"],
            "Correo informal del cliente",
            "Hola, necesitamos ordenar los pedidos porque hoy los anotamos en mensajes y a veces se pierden.",
            "email",
        )
        preview = self.service.preview_source(project["id"], source["id"])
        self.assertEqual("email", source["source_kind"])
        self.assertEqual("email", preview["source_kind"])
        self.assertIn("hoy los anotamos en mensajes", preview["text"])
        self.assertGreater(preview["fragment_count"], 0)

    def test_definition_analysis_visits_every_fragment_in_multiple_batches(self):
        fragments = [
            Fragment(f"SRC-{index:03d}-F001", f"SRC-{index:03d}", f"fuente-{index}.txt", "Texto", "Dato " + ("x" * 55))
            for index in range(1, 7)
        ]
        agent = ProjectDefinitionAgent(self.client, batch_character_limit=90)
        analysis = agent.analyze("Proyecto genérico", "", fragments)
        batch_prompts = [prompt for prompt in self.client.prompts if "Extrae hallazgos" in prompt]
        combined = "\n".join(batch_prompts)

        self.assertEqual(6, analysis["coverage"]["fragment_count"])
        self.assertEqual(6, analysis["coverage"]["batch_count"])
        self.assertEqual(6, len(batch_prompts))
        for fragment in fragments:
            self.assertIn(fragment.fragment_id, combined)


if __name__ == "__main__":
    unittest.main()
