from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from .agents import ProjectDefinitionAgent, RevisionAgent, SpecializedGenerationAgent, CONTRACTS
from .documents import DocumentExtractionService, TextSegmentationService, safe_filename
from .generation_budget import (
    normalize_generation_limits,
    recommend_generation_budgets,
    validate_generation_limits,
)
from .llm import DeepSeekClient
from .models import Artifact
from .settings import Settings
from .storage import SQLiteRepository
from .validation import TraceabilityConsistencyAgent
from .vector_store import ChromaProjectVectorStore, CrossEncoderReranker, HybridRetrievalAgent


class ProjectApplicationService:
    """Casos de uso de proyecto, ingesta, definición, generación y revisión."""

    def __init__(
        self,
        repository: SQLiteRepository,
        vector_store: ChromaProjectVectorStore,
        data_dir: str | Path,
        client: DeepSeekClient,
        settings: Settings | None = None,
        reranker: CrossEncoderReranker | None = None,
    ):
        self.repository = repository
        self.vector_store = vector_store
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.client = client
        self.settings = settings
        self.reranker = reranker
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
            stale_definition_ids = [
                fragment.fragment_id
                for fragment in self.repository.list_fragments(project_id)
                if fragment.source_id == "USR-DEF"
            ]
            fragments = self.segmenter.segment(
                extracted.text, source_code, filename, source_kind=source_kind
            )
            if not fragments:
                raise ValueError("La segmentación no produjo fragmentos utilizables.")
            self.repository.replace_source_fragments(source, fragments)
            self.repository.invalidate_after_source_change(project_id)
            self.vector_store.delete_fragments(project_id, stale_definition_ids)
            self.repository.update_source_status(source["id"], "processed")
            if index_after:
                self.vector_store.upsert_fragments(project_id, fragments)
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
        source_fragment_ids = [
            fragment.fragment_id
            for fragment in self.repository.list_fragments(project_id)
            if fragment.source_id in {source["source_code"], "USR-DEF"}
        ]
        self.vector_store.delete_fragments(project_id, source_fragment_ids)
        deleted = self.repository.delete_source_and_invalidate(project_id, source_id)
        if stored_path.exists():
            stored_path.unlink()
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

    def confirm_definition(
        self, project_id: str, reset_generation: bool = False
    ) -> dict[str, Any]:
        questions = self.repository.list_questions(project_id)
        provisional = self.repository.get_profile(project_id)
        stored_profile = provisional.get("profile", {}) if provisional else {}
        if not provisional or not (
            "provisional_profile" in stored_profile or "analysis_coverage" in stored_profile
        ):
            raise ValueError("Primero debe analizar el corpus y revisar la interpretación provisional.")
        missing = [item["question"] for item in questions if item["required"] and not item["answer"].strip()]
        if missing:
            raise ValueError(f"Faltan {len(missing)} respuestas obligatorias antes de confirmar la definición.")
        existing_artifacts = self.repository.list_artifacts(project_id)
        if existing_artifacts and not reset_generation:
            raise ValueError(
                "Este proyecto ya contiene artefactos generados. Confirme explícitamente "
                "reset_generation para eliminar la generación, sus versiones y observaciones antes de continuar."
            )
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
            "analysis_coverage": stored_profile.get(
                "coverage", stored_profile.get("analysis_coverage", {})
            ),
        }
        previous_definition_ids = [
            fragment.fragment_id
            for fragment in self.repository.list_fragments(project_id)
            if fragment.source_id == "USR-DEF"
        ]
        definition_fragments = self.repository.upsert_definition_fragments(project_id, questions)
        if existing_artifacts:
            self.repository.reset_generation_results(project_id)
        self.repository.save_profile(project_id, profile, confirmed=True)
        self.vector_store.delete_fragments(project_id, previous_definition_ids)
        self.vector_store.upsert_fragments(project_id, definition_fragments)
        return profile

    def generate_artifacts(
        self,
        project_id: str,
        limit_per_type: int | None = None,
        run_id: str | None = None,
        progress_callback: Callable[[int, str, str], None] | None = None,
        limits_by_type: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        if not project["definition_confirmed"]:
            raise ValueError("La ficha de definición debe confirmarse antes de generar artefactos.")
        fragments = self.repository.list_fragments(project_id)
        if not fragments:
            raise ValueError("El proyecto no contiene fragmentos indexados.")
        limits = normalize_generation_limits(limits_by_type, fallback=limit_per_type or 12)
        recommendations = recommend_generation_budgets(fragments)
        if limits_by_type is not None:
            limits = validate_generation_limits(limits, recommendations)
        if not self.vector_store.has_project(project_id):
            # Migración segura al espacio del modelo de embeddings configurado.
            self.vector_store.upsert_fragments(project_id, fragments)
        retriever = self._retriever(project_id, fragments)
        artifacts: list[Artifact] = []
        retrieval_log: dict[str, list[dict[str, Any]]] = {}
        telemetry_log: dict[str, dict[str, Any]] = {}
        parent_run = run_id or self.repository.start_run(
            project_id,
            "generation",
            "orchestrator.main",
            self.run_parameters(limits, recommendations),
        )
        progress = progress_callback or (lambda _percent, _message, _step: None)
        self.repository.update_project_status(project_id, "generating")
        try:
            progress(8, "Preparando la recuperación híbrida", "retrieval")
            for position, artifact_type in enumerate(("RF", "RNF", "HU"), start=1):
                contract = CONTRACTS[artifact_type]
                progress(15 + (position - 1) * 24, f"Ejecutando {contract.agent_id}", f"generating_{artifact_type.lower()}")
                child_run_id = self.repository.start_run(
                    project_id,
                    "generation",
                    contract.agent_id,
                    self.run_parameters(limits, recommendations, artifact_type),
                )
                try:
                    agent = SpecializedGenerationAgent(
                        contract,
                        retriever,
                        self.client,
                        project["name"],
                        project["domain"],
                        retrieval_top_k=self.settings.retrieval_top_k if self.settings else 24,
                    )
                    # Se inyectan los artefactos ya generados para asegurar coherencia y evitar redundancias cross-type
                    generated, evidence = agent.generate(
                        limit=limits[artifact_type], existing_artifacts=list(artifacts)
                    )
                    artifacts.extend(generated)
                    score_name = "reranker_score" if self.reranker else "rrf_score"
                    retrieval_log[artifact_type] = [
                        {"fragment_id": fragment.fragment_id, score_name: round(score, 8)}
                        for fragment, score in evidence
                    ]
                    agent_metrics = getattr(agent, "last_telemetry", {}) or {}
                    telemetry_log[artifact_type] = agent_metrics
                    self.repository.finish_run(child_run_id, "completed", metrics=agent_metrics)
                except Exception as error:
                    failure_metrics = (
                        self.client.get_last_telemetry()
                        if hasattr(self.client, "get_last_telemetry")
                        else None
                    )
                    self.repository.finish_run(
                        child_run_id, "failed", str(error), metrics=failure_metrics
                    )
                    raise
            progress(88, "Validando trazabilidad y consistencia", "validation")
            report = TraceabilityConsistencyAgent(
                duplicate_threshold=self.settings.duplicate_threshold if self.settings else 0.72,
                cross_type_duplicate_threshold=(
                    self.settings.cross_type_duplicate_threshold if self.settings else 0.55
                ),
            ).validate(artifacts, fragments)
            self.repository.save_artifacts(project_id, artifacts)
            self.repository.save_validation_report(project_id, report)
            progress(100, "Artefactos disponibles para revisión", "completed")

            # Métricas agregadas para el parent run
            total_latency = sum(item.get("latency_ms", 0.0) for item in telemetry_log.values())
            total_tokens = sum(item.get("total_tokens", 0) or 0 for item in telemetry_log.values())
            total_attempts = sum(item.get("attempts", 1) for item in telemetry_log.values())
            generated_counts = {
                artifact_type: sum(1 for artifact in artifacts if artifact.artifact_type == artifact_type)
                for artifact_type in ("RF", "RNF", "HU")
            }
            summary_metrics = {
                "total_latency_ms": round(total_latency, 2),
                "total_tokens": total_tokens or None,
                "total_attempts": total_attempts,
                "generated_counts": generated_counts,
                "budget_saturation": {
                    artifact_type: generated_counts[artifact_type] >= limits[artifact_type]
                    for artifact_type in generated_counts
                },
                "agents": telemetry_log,
            }
            self.repository.finish_run(parent_run, "completed", metrics=summary_metrics)
            return {
                "artifacts": artifacts,
                "validation": report,
                "retrieval": retrieval_log,
                "telemetry": summary_metrics,
            }
        except Exception as error:
            self.repository.finish_run(parent_run, "failed", str(error))
            self.repository.update_project_status(project_id, "ready_to_generate")
            raise

    def propose_revision(self, project_id: str, artifact_id: str, instruction: str) -> Artifact:
        if not instruction.strip():
            raise ValueError("Indique qué desea mejorar en el artefacto.")
        fragments = self.repository.list_fragments(project_id)
        retriever = self._retriever(project_id, fragments)
        return RevisionAgent(self.client, retriever).propose(self.repository.get_artifact(artifact_id), instruction)

    def accept_revision(self, artifact_id: str, proposal: Artifact, instruction: str) -> dict[str, Any]:
        updated = self.repository.update_artifact(artifact_id, proposal, "ai_revision", instruction)
        self._refresh_validation(updated["project_id"])
        return self.repository.get_artifact(artifact_id)

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
        target_type = str(values.get("artifact_type") or current["artifact_type"])
        if target_type not in {"RF", "RNF", "HU"}:
            raise ValueError("El tipo de artefacto debe ser RF, RNF o HU.")
        artifact = Artifact(
            artifact_id=current["artifact_key"],
            artifact_type=target_type,
            title=str(values.get("title", current["title"])).strip(),
            description=str(values.get("description", current["description"])).strip(),
            priority=str(values.get("priority", current["priority"])),
            source_fragments=list(values.get("source_fragments", current["source_fragments"])),
            status=str(values.get("status", current["status"])),
            acceptance_criteria=list(values.get("acceptance_criteria", current["acceptance_criteria"])),
            related_artifacts=list(
                current.get("related_artifacts", [])
                if values.get("related_artifacts") is None
                else values["related_artifacts"]
            ),
        )
        origin = (
            "manual_reclassification"
            if target_type != current["artifact_type"]
            else "manual_revision"
        )
        updated = self.repository.update_artifact(artifact_id, artifact, origin)
        self._refresh_validation(updated["project_id"])
        return self.repository.get_artifact(artifact_id)

    def approve_all_artifacts(self, project_id: str) -> dict[str, Any]:
        self.repository.get_project(project_id)
        artifacts = self.repository.list_artifacts(project_id)
        if not artifacts:
            raise ValueError("El proyecto todavía no tiene artefactos para aprobar.")
        approved_count = self.repository.approve_all_artifacts(project_id)
        self._refresh_validation(project_id)
        return {
            "approved_count": approved_count,
            "total_count": len(artifacts),
            "artifacts": self.repository.list_artifacts(project_id),
        }

    def _refresh_validation(self, project_id: str) -> None:
        artifacts = [
            Artifact.from_dict(item | {"artifact_id": item["artifact_key"]}, item["artifact_type"], index)
            for index, item in enumerate(self.repository.list_artifacts(project_id), start=1)
        ]
        report = TraceabilityConsistencyAgent(
            duplicate_threshold=self.settings.duplicate_threshold if self.settings else 0.72,
            cross_type_duplicate_threshold=(
                self.settings.cross_type_duplicate_threshold if self.settings else 0.55
            ),
        ).validate(artifacts, self.repository.list_fragments(project_id))
        self.repository.save_validation_report(project_id, report)

    def _retriever(self, project_id: str, fragments: list) -> HybridRetrievalAgent:
        return HybridRetrievalAgent(
            project_id,
            fragments,
            self.vector_store,
            lexical_weight=self.settings.rrf_lexical_weight if self.settings else 0.45,
            semantic_weight=self.settings.rrf_semantic_weight if self.settings else 0.55,
            reranker=self.reranker,
        )

    def generation_recommendations(self, project_id: str) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        if not project["definition_confirmed"]:
            raise ValueError("La definición del proyecto debe estar confirmada.")
        return recommend_generation_budgets(self.repository.list_fragments(project_id))

    def run_parameters(
        self,
        limits_by_type: dict[str, int] | int,
        recommendations: dict[str, Any] | None = None,
        active_artifact_type: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(limits_by_type, int):
            limits = normalize_generation_limits(fallback=limits_by_type)
        else:
            limits = normalize_generation_limits(limits_by_type)
        parameters: dict[str, Any] = {
            "model": self.client.model,
            "generation_limits": limits,
            "generation_budget_method": (recommendations or {}).get("method_version"),
            "generation_budget_recommendations": recommendations,
            "retrieval": "hybrid_rrf",
            "generation_order": ["RF", "RNF", "HU"],
            "agent_retrieval_queries": {
                artifact_type: contract.retrieval_query
                for artifact_type, contract in CONTRACTS.items()
            },
        }
        if len(set(limits.values())) == 1:
            parameters["limit_per_type"] = next(iter(limits.values()))
        if active_artifact_type:
            parameters["active_artifact_type"] = active_artifact_type
            parameters["active_limit"] = limits[active_artifact_type]
        if self.settings:
            parameters["experimental_config"] = self.settings.experimental_snapshot()
        return parameters

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
            {key: item[key] for key in ("artifact_key", "artifact_type", "title", "description", "priority", "source_fragments", "status", "acceptance_criteria", "related_artifacts", "validation", "version")}
            for item in repository.list_artifacts(project_id)
        ],
        "validation": (repository.latest_validation_report(project_id) or {}).get("report", {}),
        "generation_run": repository.latest_run(project_id),
    }


def project_export_json(repository: SQLiteRepository, project_id: str) -> bytes:
    return json.dumps(project_export_payload(repository, project_id), ensure_ascii=False, indent=2).encode("utf-8")
