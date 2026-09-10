from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from .agents import ProjectDefinitionAgent, RevisionAgent, SpecializedGenerationAgent, CONTRACTS
from .documents import DocumentExtractionService, TextSegmentationService, safe_filename
from .llm import DeepSeekClient
from .models import Artifact
from .settings import Settings
from .storage import SQLiteRepository
from .validation import TraceabilityConsistencyAgent
from .vector_store import ChromaProjectVectorStore, HybridRetrievalAgent


class ProjectApplicationService:
    """Casos de uso de proyecto, ingesta, definición, generación y revisión."""

    def __init__(
        self,
        repository: SQLiteRepository,
        vector_store: ChromaProjectVectorStore,
        data_dir: str | Path,
        client: DeepSeekClient,
        settings: Settings | None = None,
    ):
        self.repository = repository
        self.vector_store = vector_store
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.client = client
        self.settings = settings
        chunk_size = settings.chunk_size if settings else 1200
        chunk_overlap = settings.chunk_overlap if settings else 180
        self.extractor = DocumentExtractionService()
        self.segmenter = TextSegmentationService(chunk_size=chunk_size, overlap=chunk_overlap)
        self.definition_agent = ProjectDefinitionAgent(client)

    def create_project(self, name: str, description: str = "", domain: str = "") -> dict[str, Any]:
        if not name.strip():
            raise ValueError("El proyecto necesita un nombre.")
        project = self.repository.create_project(name, description, domain)
        self.repository.ensure_questions(project["id"], list(ProjectDefinitionAgent.CORE_QUESTIONS))
        return project

    def archive_project(self, project_id: str, archived: bool) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        if project["status"] == "generating":
            raise ValueError("No se puede archivar un proyecto mientras genera artefactos.")
        return self.repository.archive_project(project_id, archived)

    def delete_project(self, project_id: str) -> None:
        project = self.repository.get_project(project_id)
        if project["status"] == "generating":
            raise ValueError("No se puede eliminar un proyecto mientras genera artefactos.")
        self.vector_store.delete_project(project_id)
        self.repository.delete_project(project_id)
        project_folder = self._project_folder(project_id)
        if project_folder.exists():
            shutil.rmtree(project_folder)

    def ingest(
        self,
        project_id: str,
        filename: str,
        content: bytes,
        content_type: str = "",
        index_after: bool = True,
        source_kind: str = "document",
    ) -> dict[str, Any]:
        extracted = self.extractor.extract(filename, content)
        duplicate = self.repository.find_source_by_hash(project_id, extracted.sha256)
        if duplicate:
            raise ValueError(f"La fuente ya fue cargada como {duplicate['source_code']}: {duplicate['original_name']}")
        source_code = self.repository.next_source_code(project_id)
        project_folder = self.data_dir / "projects" / project_id / "sources"
        project_folder.mkdir(parents=True, exist_ok=True)
        stored_name = f"{source_code}_{uuid.uuid4().hex[:8]}_{safe_filename(filename)}"
        stored_path = project_folder / stored_name
        stored_path.write_bytes(content)
        source = self.repository.add_source(
            project_id,
            source_code,
            filename,
            str(stored_path),
            content_type,
            extracted.sha256,
            source_kind,
        )
        try:
            fragments = self.segmenter.segment(extracted.text, source_code, filename)
            if not fragments:
                raise ValueError("La segmentación no produjo fragmentos utilizables.")
            self.repository.replace_source_fragments(source, fragments)
            self.repository.invalidate_after_source_change(project_id)
            self.repository.update_source_status(source["id"], "processed")
            if index_after:
                self.reindex(project_id)
                self.repository.mark_project_sources_indexed(project_id)
            self.repository.update_project_status(project_id, "sources_ready")
        except Exception as error:
            self.repository.update_source_status(source["id"], "error", str(error))
            raise
        return self.repository.get_source(source["id"])

    def ingest_text(
        self,
        project_id: str,
        title: str,
        text: str,
        source_kind: str,
    ) -> dict[str, Any]:
        clean_title = title.strip()
        clean_text = text.strip()
        allowed_kinds = {"email", "interview", "meeting_notes", "conversation", "note", "other"}
        if source_kind not in allowed_kinds:
            raise ValueError("El tipo de fuente textual no es válido.")
        if len(clean_title) < 2:
            raise ValueError("La fuente necesita un título.")
        if len(clean_text) < 20:
            raise ValueError("El texto debe contener al menos 20 caracteres.")
        display_title = clean_title.replace("/", "-").replace("\\", "-").replace("\n", " ").replace("\r", " ")
        filename = f"{display_title}.txt"
        return self.ingest(
            project_id,
            filename,
            clean_text.encode("utf-8"),
            "text/plain; charset=utf-8",
            source_kind=source_kind,
        )

    def preview_source(self, project_id: str, source_id: str) -> dict[str, Any]:
        source = self.repository.get_project_source(project_id, source_id)
        stored_path = self._stored_source_path(project_id, source["stored_path"])
        if not stored_path.is_file():
            raise FileNotFoundError(f"No se encontró el archivo original de {source['original_name']}.")
        extracted = self.extractor.extract(source["original_name"], stored_path.read_bytes())
        return {
            "id": source["id"],
            "source_code": source["source_code"],
            "original_name": source["original_name"],
            "content_type": source["content_type"],
            "source_kind": source.get("source_kind", "document"),
            "text": extracted.text,
            "character_count": len(extracted.text),
            "fragment_count": len(
                self.repository.list_fragment_summaries(project_id, source["source_code"])
            ),
        }

    def delete_source(self, project_id: str, source_id: str) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        if project["status"] == "generating":
            raise ValueError("No se puede eliminar una fuente mientras se generan artefactos.")
        source = self.repository.get_project_source(project_id, source_id)
        stored_path = self._stored_source_path(project_id, source["stored_path"])
        self.vector_store.delete_project(project_id)
        deleted = self.repository.delete_source_and_invalidate(project_id, source_id)
        if stored_path.exists():
            stored_path.unlink()
        remaining_fragments = self.repository.list_fragments(project_id)
        if remaining_fragments:
            self.vector_store.index(project_id, remaining_fragments)
        return deleted

    def reindex(self, project_id: str) -> None:
        fragments = self.repository.list_fragments(project_id)
        self.vector_store.index(project_id, fragments)

    def analyze_definition(self, project_id: str) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        fragments = [
            fragment
            for fragment in self.repository.list_fragments(project_id)
            if fragment.source_id != "USR-DEF"
        ]
        if not fragments:
            raise ValueError("Primero debe cargar y procesar al menos una fuente.")
        analysis = self.definition_agent.analyze(
            project["name"], project["domain"], fragments
        )
        self.repository.replace_definition_analysis(
            project_id, list(ProjectDefinitionAgent.CORE_QUESTIONS), analysis
        )
        return analysis

    def confirm_definition(self, project_id: str) -> dict[str, Any]:
        questions = self.repository.list_questions(project_id)
        provisional = self.repository.get_profile(project_id)
        if not provisional or "provisional_profile" not in provisional.get("profile", {}):
            raise ValueError("Primero debe analizar el corpus y revisar la interpretación provisional.")
        missing = [item["question"] for item in questions if item["required"] and not item["answer"].strip()]
        if missing:
            raise ValueError(f"Faltan {len(missing)} respuestas obligatorias antes de confirmar la definición.")
        profile = {
            "project_goal": self._definition_value(questions, "DEF-OBJ", "project_goal"),
            "problem": self._definition_value(questions, "DEF-PROBLEM", "problem"),
            "actors": self._definition_value(questions, "DEF-ACTORS", "actors"),
            "scope": self._definition_value(questions, "DEF-SCOPE", "scope"),
            "out_of_scope": self._definition_value(questions, "DEF-OUT", "out_of_scope"),
            "business_and_legal_constraints": self._definition_value(
                questions, "DEF-RULES", "business_and_legal_constraints"
            ),
            "quality_expectations": self._definition_value(
                questions, "DEF-QUALITY", "quality_expectations"
            ),
            "known_conflicts": self._definition_value(
                questions, "DEF-CONFLICTS", "known_conflicts"
            ),
            "resolved_questions": [
                {"question_key": item["question_key"], "question": item["question"], "answer": item["answer"]}
                for item in questions
            ],
            "pending_questions": [],
            "analysis_coverage": provisional["profile"].get("coverage", {}),
        }
        self.repository.upsert_definition_fragments(project_id, questions)
        self.repository.save_profile(project_id, profile, confirmed=True)
        self.reindex(project_id)
        return profile

    def generate_artifacts(
        self,
        project_id: str,
        limit_per_type: int = 15,
        run_id: str | None = None,
        progress_callback: Callable[[int, str, str], None] | None = None,
    ) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        if not project["definition_confirmed"]:
            raise ValueError("La ficha de definición debe confirmarse antes de generar artefactos.")
        fragments = self.repository.list_fragments(project_id)
        if not fragments:
            raise ValueError("El proyecto no contiene fragmentos indexados.")
        retriever = HybridRetrievalAgent(
            project_id,
            fragments,
            self.vector_store,
            lexical_weight=self.settings.rrf_lexical_weight if self.settings else 0.45,
            semantic_weight=self.settings.rrf_semantic_weight if self.settings else 0.55,
        )
        artifacts: list[Artifact] = []
        retrieval_log: dict[str, list[dict[str, Any]]] = {}
        parent_run = run_id or self.repository.start_run(
            project_id,
            "generation",
            "orchestrator.main",
            {"model": self.client.model, "limit_per_type": limit_per_type, "retrieval": "hybrid_rrf"},
        )
        progress = progress_callback or (lambda _percent, _message, _step: None)
        self.repository.update_project_status(project_id, "generating")
        try:
            progress(8, "Preparando la recuperación híbrida", "retrieval")
            for position, artifact_type in enumerate(("RF", "RNF", "HU"), start=1):
                contract = CONTRACTS[artifact_type]
                progress(15 + (position - 1) * 24, f"Ejecutando {contract.agent_id}", f"generating_{artifact_type.lower()}")
                child_run_id = self.repository.start_run(project_id, "generation", contract.agent_id)
                try:
                    agent = SpecializedGenerationAgent(
                        contract,
                        retriever,
                        self.client,
                        project["name"],
                        project["domain"],
                    )
                    generated, evidence = agent.generate(limit=limit_per_type)
                    artifacts.extend(generated)
                    retrieval_log[artifact_type] = [
                        {"fragment_id": fragment.fragment_id, "rrf_score": round(score, 8)}
                        for fragment, score in evidence
                    ]
                    self.repository.finish_run(child_run_id, "completed")
                except Exception as error:
                    self.repository.finish_run(child_run_id, "failed", str(error))
                    raise
            progress(88, "Validando trazabilidad y consistencia", "validation")
            report = TraceabilityConsistencyAgent().validate(artifacts, fragments)
            self.repository.save_artifacts(project_id, artifacts)
            self.repository.save_validation_report(project_id, report)
            progress(100, "Artefactos disponibles para revisión", "completed")
            self.repository.finish_run(parent_run, "completed")
            return {"artifacts": artifacts, "validation": report, "retrieval": retrieval_log}
        except Exception as error:
            self.repository.finish_run(parent_run, "failed", str(error))
            self.repository.update_project_status(project_id, "ready_to_generate")
            raise

    def propose_revision(self, project_id: str, artifact_id: str, instruction: str) -> Artifact:
        if not instruction.strip():
            raise ValueError("Indique qué desea mejorar en el artefacto.")
        fragments = self.repository.list_fragments(project_id)
        retriever = HybridRetrievalAgent(project_id, fragments, self.vector_store)
        return RevisionAgent(self.client, retriever).propose(self.repository.get_artifact(artifact_id), instruction)

    def accept_revision(self, artifact_id: str, proposal: Artifact, instruction: str) -> dict[str, Any]:
        return self.repository.update_artifact(artifact_id, proposal, "ai_revision", instruction)

    def create_revision_proposal(self, project_id: str, artifact_id: str, instruction: str) -> dict[str, Any]:
        proposal = self.propose_revision(project_id, artifact_id, instruction)
        return self.repository.create_revision_proposal(project_id, artifact_id, proposal, instruction)

    def decide_revision_proposal(self, proposal_id: str, accept: bool) -> dict[str, Any]:
        proposal = self.repository.get_revision_proposal(proposal_id)
        if proposal["status"] != "pending":
            raise ValueError("La propuesta ya fue decidida.")
        if accept:
            current = self.repository.get_artifact(proposal["artifact_id"])
            artifact = Artifact.from_dict(proposal["proposal"], current["artifact_type"], 1)
            self.accept_revision(current["id"], artifact, proposal["instruction"])
            return self.repository.decide_revision_proposal(proposal_id, "accepted")
        return self.repository.decide_revision_proposal(proposal_id, "rejected")

    def save_manual_revision(self, artifact_id: str, values: dict[str, Any]) -> dict[str, Any]:
        current = self.repository.get_artifact(artifact_id)
        artifact = Artifact(
            artifact_id=current["artifact_key"],
            artifact_type=current["artifact_type"],
            title=str(values.get("title", current["title"])).strip(),
            description=str(values.get("description", current["description"])).strip(),
            priority=str(values.get("priority", current["priority"])),
            source_fragments=list(values.get("source_fragments", current["source_fragments"])),
            status=str(values.get("status", current["status"])),
            acceptance_criteria=list(values.get("acceptance_criteria", current["acceptance_criteria"])),
        )
        return self.repository.update_artifact(artifact_id, artifact, "manual_revision")

    @staticmethod
    def _answer(questions: list[dict[str, Any]], key: str) -> str:
        return next((item["answer"] for item in questions if item["question_key"] == key), "")

    @classmethod
    def _definition_value(
        cls, questions: list[dict[str, Any]], key: str, dimension: str
    ) -> str:
        base = cls._answer(questions, key).strip()
        clarifications = [
            f"{item['question']} {item['answer'].strip()}"
            for item in questions
            if item.get("origin") == "dynamic"
            and item.get("dimension") == dimension
            and item.get("answer", "").strip()
        ]
        if not clarifications:
            return base
        suffix = "\n".join(f"- {value}" for value in clarifications)
        return f"{base}\nAclaraciones confirmadas:\n{suffix}".strip()

    def _project_folder(self, project_id: str) -> Path:
        projects_root = (self.data_dir / "projects").resolve()
        project_folder = (projects_root / project_id).resolve()
        if project_folder.parent != projects_root:
            raise RuntimeError("La ruta del proyecto no pertenece al directorio de datos.")
        return project_folder

    def _stored_source_path(self, project_id: str, stored_path: str) -> Path:
        sources_folder = (self._project_folder(project_id) / "sources").resolve()
        candidate = Path(stored_path).resolve()
        if candidate.parent != sources_folder:
            raise RuntimeError("La ruta de la fuente no pertenece al proyecto.")
        return candidate


def project_export_payload(repository: SQLiteRepository, project_id: str) -> dict[str, Any]:
    project = repository.get_project(project_id)
    return {
        "project": {
            "id": project["id"],
            "name": project["name"],
            "description": project["description"],
            "domain": project["domain"],
            "status": project["status"],
        },
        "profile": (repository.get_profile(project_id) or {}).get("profile", {}),
        "sources": [
            {key: item[key] for key in ("source_code", "original_name", "content_type", "source_kind", "sha256", "status")}
            for item in repository.list_sources(project_id)
        ],
        "artifacts": [
            {key: item[key] for key in ("artifact_key", "artifact_type", "title", "description", "priority", "source_fragments", "status", "acceptance_criteria", "version")}
            for item in repository.list_artifacts(project_id)
        ],
        "validation": (repository.latest_validation_report(project_id) or {}).get("report", {}),
    }


def project_export_json(repository: SQLiteRepository, project_id: str) -> bytes:
    return json.dumps(project_export_payload(repository, project_id), ensure_ascii=False, indent=2).encode("utf-8")
