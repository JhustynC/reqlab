from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Protocol

from .llm import LLMClient
from .models import Artifact, Fragment


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int = 12) -> list[tuple[Fragment, float]]: ...


@dataclass(frozen=True)
class AgentContract:
    agent_id: str
    role: str
    artifact_type: str
    task: str
    quality_rules: tuple[str, ...]
    retrieval_query: str = ""


CONTRACTS = {
    "RF": AgentContract(
        "agent.rf",
        "Analista especializado en requisitos funcionales",
        "RF",
        "Identificar capacidades y comportamientos observables que el sistema debe proporcionar.",
        (
            "Redactar cada requisito con sujeto y comportamiento verificable.",
            "Separar capacidades distintas y evitar decisiones de diseño no sustentadas.",
            "No clasificar atributos de calidad como funciones.",
        ),
        retrieval_query=(
            "capacidades funcionales procesos acciones comportamientos observables "
            "el sistema debe permitir registrar consultar modificar gestionar"
        ),
    ),
    "RNF": AgentContract(
        "agent.rnf",
        "Analista especializado en requisitos no funcionales",
        "RNF",
        "Identificar atributos de calidad, restricciones y condiciones medibles del sistema.",
        (
            "No convertir funciones del negocio en requisitos no funcionales.",
            "Conservar las métricas explícitas de las fuentes; no inventar umbrales.",
            "Marcar como pendiente cualquier atributo que no pueda verificarse con la información disponible.",
        ),
        retrieval_query=(
            "rendimiento tiempo respuesta disponibilidad seguridad autenticación "
            "cifrado retención datos usabilidad escalabilidad restricción normativa legal"
        ),
    ),
    "HU": AgentContract(
        "agent.hu",
        "Analista especializado en historias de usuario",
        "HU",
        "Expresar necesidades de los actores con valor observable y criterios de aceptación.",
        (
            "Usar el patrón Como [rol], quiero [objetivo], para [beneficio].",
            "Añadir criterios de aceptación concretos y trazables.",
            "No inventar actores ni beneficios ausentes de las fuentes o de la definición confirmada.",
        ),
        retrieval_query=(
            "actor usuario rol administrador cliente empleado necesita quiere beneficio "
            "escenario flujo interacción objetivo valor"
        ),
    ),
}



class SpecializedGenerationAgent:
    """Agente LLM con identidad, responsabilidad y contrato de salida explícitos."""

    def __init__(
        self,
        contract: AgentContract,
        retriever: Retriever,
        client: LLMClient,
        project_name: str,
        domain: str,
        retrieval_top_k: int = 24,
    ):
        self.contract = contract
        self.retriever = retriever
        self.client = client
        self.project_name = project_name
        self.domain = domain or "dominio descrito por las fuentes"
        self.retrieval_top_k = retrieval_top_k
        self.last_telemetry: dict[str, Any] = {}

    def generate(
        self,
        limit: int = 15,
        existing_artifacts: list[Artifact] | None = None,
    ) -> tuple[list[Artifact], list[tuple[Fragment, float]]]:
        # Construir query enriquecida: nombre + dominio + tarea genérica + términos especializados del tipo
        specialized = self.contract.retrieval_query or self.contract.task
        query = f"{self.project_name} {self.domain} {specialized}"
        evidence = self.retriever.retrieve(query, top_k=self.retrieval_top_k)
        if not evidence:
            raise RuntimeError(f"{self.contract.agent_id} no recuperó evidencia suficiente para generar artefactos.")
        from .llm_schemas import ArtifactsResponse
        validation_context = {
            "artifact_type": self.contract.artifact_type,
            "valid_citations": [fragment.fragment_id for fragment, _ in evidence],
            "valid_relations": [artifact.artifact_id for artifact in (existing_artifacts or [])],
        }
        validated_completion = getattr(self.client, "complete_json_validated", None)
        if callable(validated_completion):
            response = validated_completion(
                system_prompt=(
                    f"Actúas como {self.contract.role}. Trabajas únicamente con evidencia citada. "
                    "Responde en español y devuelve exclusivamente JSON válido."
                ),
                user_prompt=self._prompt(evidence, limit, existing_artifacts or []),
                schema=ArtifactsResponse,
                validation_context=validation_context,
            )
            records = [record.model_dump() for record in response.artifacts]
        else:
            # Compatibilidad exclusiva con clientes de prueba/legado que no ofrecen
            # validación. Un fallo real de validación nunca se omite con otra llamada.
            payload = self.client.complete_json(
                system_prompt=(
                    f"Actúas como {self.contract.role}. Trabajas únicamente con evidencia citada. "
                    "Responde en español y devuelve exclusivamente JSON válido."
                ),
                user_prompt=self._prompt(evidence, limit, existing_artifacts or []),
            )
            response = ArtifactsResponse.model_validate(payload, context=validation_context)
            records = [record.model_dump() for record in response.artifacts]

        if hasattr(self.client, "get_last_telemetry"):
            self.last_telemetry = self.client.get_last_telemetry()
        self.last_telemetry["returned_artifacts"] = len(records)
        self.last_telemetry["accepted_artifacts"] = min(len(records), limit)
        self.last_telemetry["truncated_to_budget"] = len(records) > limit

        artifacts = [
            Artifact.from_dict(self._normalize_record(item, index), self.contract.artifact_type, index)
            for index, item in enumerate(records[:limit], start=1)
        ]
        return artifacts, evidence

    def _normalize_record(self, record: dict[str, Any], index: int) -> dict[str, Any]:
        normalized = dict(record)
        normalized["artifact_id"] = f"{self.contract.artifact_type}-{index:03d}"
        return normalized

    def _prompt(
        self,
        evidence: list[tuple[Fragment, float]],
        limit: int,
        existing_artifacts: list[Artifact],
    ) -> str:
        context = "\n\n".join(
            f"[{fragment.fragment_id}] {fragment.heading}\n{fragment.text}" for fragment, _ in evidence
        )
        allowed_citations = [fragment.fragment_id for fragment, _ in evidence]
        allowed_relations = [artifact.artifact_id for artifact in existing_artifacts]
        schema = {
            "artifact_id": f"{self.contract.artifact_type}-001",
            "title": "Título breve",
            "description": "Enunciado completo",
            "priority": "Alta|Media|Baja",
            "source_fragments": [allowed_citations[0]],
            "status": "propuesto|requiere aclaración",
            "acceptance_criteria": (
                ["Criterio verificable"] if self.contract.artifact_type == "HU" else []
            ),
            "related_artifacts": allowed_relations[:1],
        }
        rules = "\n".join(f"- {rule}" for rule in self.contract.quality_rules)

        coherence_section = ""
        if existing_artifacts:
            # Se preservan todos los artefactos previos dentro de los presupuestos
            # configurados, evitando truncar RNF al generar HU.
            summary_lines = [
                f"- [{a.artifact_id} ({a.artifact_type}); estado={a.status}] {a.title}: {a.description}"
                for a in existing_artifacts
            ]
            coherence_guide = ""
            if self.contract.artifact_type == "HU":
                coherence_guide = (
                    "Alinea las Historias de Usuario con las capacidades de los Requisitos Funcionales anteriores. "
                    "Expresa la perspectiva de valor del actor sin duplicar literalmente el texto del RF."
                )
            elif self.contract.artifact_type == "RNF":
                coherence_guide = (
                    "Formula atributos de calidad, rendimiento o seguridad que apliquen sobre las funciones anteriores, "
                    "sin redactar comportamientos funcionales."
                )
            else:
                coherence_guide = "Mantén consistencia y evita duplicar o contradecir los artefactos existentes."

            coherence_section = f"""
Artefactos del proyecto ya identificados (mantener coherencia con ellos):
{coherence_guide}
Estos artefactos son contexto generado, no evidencia documental. No los uses como source_fragments ni conviertas una incertidumbre en un hecho.
""" + "\n".join(summary_lines) + "\n"

        return f"""Proyecto: {self.project_name}
Dominio: {self.domain}
Tarea exclusiva del agente: {self.contract.task}

Reglas especializadas:
{rules}

Reglas comunes:
- El valor {limit} es un presupuesto máximo, no una cuota que debas completar.
- Genera únicamente artefactos sustentados por la evidencia y devuelve menos de {limit} si no existe información suficiente.
- No dividas, repitas ni inventes artefactos para alcanzar el máximo disponible.
- Usa solamente la evidencia proporcionada.
- Cada artefacto debe citar uno o más identificadores exactos presentes en el contexto.
- Identificadores de cita permitidos: {json.dumps(allowed_citations, ensure_ascii=False)}.
- source_fragments solo puede contener evidencia documental; no cites identificadores RF/RNF/HU como fuentes.
- Identificadores de relación permitidos: {json.dumps(allowed_relations, ensure_ascii=False)}. Si la lista está vacía, usa related_artifacts: [].
- related_artifacts solo puede contener identificadores RF/RNF/HU mostrados en la sección de coherencia.
- Si falta información, conserva la incertidumbre y usa el estado 'requiere aclaración'.
- No resuelvas contradicciones mediante suposiciones.
- Devuelve {{"artifacts": [...]}} usando este esquema: {json.dumps(schema, ensure_ascii=False)}
{coherence_section}
Evidencia recuperada:
{context}"""




class ProjectDefinitionAgent:
    """Interpreta todo el corpus y pregunta únicamente por vacíos o decisiones pendientes."""

    DIMENSIONS = (
        "project_goal",
        "problem",
        "actors",
        "scope",
        "out_of_scope",
        "business_and_legal_constraints",
        "quality_expectations",
        "known_conflicts",
    )
    CORE_QUESTIONS = (
        {
            "question_key": "DEF-OBJ", "dimension": "project_goal",
            "question": "Objetivo principal del sistema",
            "rationale": "Describe el resultado que se espera obtener con el producto.", "required": False,
        },
        {
            "question_key": "DEF-PROBLEM", "dimension": "problem",
            "question": "Problema o situación que se desea mejorar",
            "rationale": "Relaciona el sistema con una necesidad observable.", "required": False,
        },
        {
            "question_key": "DEF-ACTORS", "dimension": "actors",
            "question": "Actores y responsabilidades identificadas",
            "rationale": "Fundamenta las funciones y las historias de usuario.", "required": False,
        },
        {
            "question_key": "DEF-SCOPE", "dimension": "scope",
            "question": "Procesos y capacidades dentro del alcance",
            "rationale": "Establece la frontera funcional del proyecto.", "required": False,
        },
        {
            "question_key": "DEF-OUT", "dimension": "out_of_scope",
            "question": "Exclusiones o elementos fuera del alcance",
            "rationale": "Evita incorporar funciones no acordadas.", "required": False,
        },
        {
            "question_key": "DEF-RULES", "dimension": "business_and_legal_constraints",
            "question": "Reglas de negocio y restricciones aplicables",
            "rationale": "Identifica las condiciones que limitan el comportamiento del sistema.", "required": False,
        },
        {
            "question_key": "DEF-QUALITY", "dimension": "quality_expectations",
            "question": "Expectativas de calidad verificables",
            "rationale": "Recoge seguridad, rendimiento, disponibilidad, usabilidad y conservación de datos.", "required": False,
        },
        {
            "question_key": "DEF-CONFLICTS", "dimension": "known_conflicts",
            "question": "Vacíos, ambigüedades y contradicciones detectadas",
            "rationale": "Mantiene visibles las decisiones que ReqLab no debe resolver por su cuenta.", "required": False,
        },
    )

    def __init__(
        self,
        client: LLMClient,
        batch_character_limit: int = 18000,
        max_workers: int = 3,
    ):
        if batch_character_limit < 1:
            raise ValueError("batch_character_limit debe ser mayor que cero.")
        if max_workers < 1:
            raise ValueError("max_workers debe ser al menos 1.")
        self.client = client
        self.batch_character_limit = batch_character_limit
        self.max_workers = max_workers
        self._telemetry: ContextVar[dict[str, Any]] = ContextVar(
            f"definition_telemetry_{id(self)}", default={}
        )

    def get_last_telemetry(self) -> dict[str, Any]:
        return {key: value for key, value in self._telemetry.get().items() if key != "_lock"}

    def analyze(
        self,
        project_name: str,
        domain: str,
        fragments: list[Fragment],
        maximum_questions: int = 10,
        progress_callback: Callable[[int, str, str], None] | None = None,
    ) -> dict[str, Any]:
        if not fragments:
            raise ValueError("No hay fragmentos para analizar.")
        self._telemetry.set({"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "_lock": Lock()})
        progress = progress_callback or (lambda _percent, _message, _step: None)
        batches = self._batches(fragments)
        progress(3, f"Corpus dividido en {len(batches)} bloques", "preparing")
        summaries: list[dict[str, Any] | None] = [None] * len(batches)
        worker_count = min(self.max_workers, len(batches))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(copy_context().run, self._analyze_batch, project_name, domain, batch): index
                for index, batch in enumerate(batches)
            }
            completed = 0
            for future in as_completed(futures):
                index = futures[future]
                summaries[index] = future.result()
                completed += 1
                percent = 5 + round((completed / len(batches)) * 62)
                progress(
                    percent,
                    f"Bloque {completed} de {len(batches)} analizado",
                    "analyzing_batches",
                )
        complete_summaries = [summary for summary in summaries if summary is not None]
        progress(72, "Consolidando hallazgos y contradicciones", "consolidating")
        summaries = self._compress_summaries(
            project_name,
            domain,
            complete_summaries,
            progress_callback=progress,
        )
        from .llm_schemas import DefinitionAnalysisResponse

        progress(86, "Construyendo la interpretación provisional", "synthesizing")
        payload = self._complete_validated(
            DefinitionAnalysisResponse,
            system_prompt=(
                "Eres un analista de requisitos en una etapa de elicitación. Construye una interpretación "
                "provisional sustentada, conserva las contradicciones y no generes RF, RNF ni historias de usuario. "
                "Devuelve exclusivamente JSON válido."
            ),
            user_prompt=self._synthesis_prompt(project_name, domain, summaries, maximum_questions),
        )
        result = self._normalize_analysis(payload, fragments, maximum_questions, len(batches))
        progress(97, "Guardando perfil y preguntas adaptativas", "saving")
        return result

    def _complete_validated(self, schema: type, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        try:
            validated_completion = getattr(self.client, "complete_json_validated", None)
            if callable(validated_completion):
                return validated_completion(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=schema,
                ).model_dump()
            return schema.model_validate(
                self.client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
            ).model_dump()
        finally:
            if hasattr(self.client, "get_last_telemetry"):
                call = self.client.get_last_telemetry()
                aggregate = self._telemetry.get()
                lock = aggregate.setdefault("_lock", Lock())
                with lock:
                    for key in ("total_tokens", "prompt_tokens", "completion_tokens", "latency_ms", "attempts"):
                        aggregate[key] = (aggregate.get(key) or 0) + (call.get(key) or 0)
                    aggregate["calls"] = (aggregate.get("calls") or 0) + 1

    def _batches(self, fragments: list[Fragment]) -> list[list[Fragment]]:
        batches: list[list[Fragment]] = []
        current: list[Fragment] = []
        current_size = 0
        for fragment in fragments:
            rendered_size = len(fragment.fragment_id) + len(fragment.heading) + len(fragment.text) + 10
            if current and current_size + rendered_size > self.batch_character_limit:
                batches.append(current)
                current = []
                current_size = 0
            current.append(fragment)
            current_size += rendered_size
        if current:
            batches.append(current)
        return batches

    def _analyze_batch(
        self, project_name: str, domain: str, fragments: list[Fragment]
    ) -> dict[str, Any]:
        context = "\n\n".join(
            f"[{fragment.fragment_id}] {fragment.heading}\n{fragment.text}" for fragment in fragments
        )
        from .llm_schemas import DefinitionBatchResponse

        payload = self._complete_validated(
            DefinitionBatchResponse,
            system_prompt=(
                "Analiza el bloque completo de fuentes como evidencia de elicitación. No redactes requisitos, "
                "no completes vacíos con conocimiento externo y devuelve exclusivamente JSON válido."
            ),
            user_prompt=f"""Proyecto: {project_name}
Dominio declarado: {domain or 'no especificado'}

Extrae hallazgos para estas dimensiones: {', '.join(self.DIMENSIONS)}.
Registra también ausencias, ambigüedades, contradicciones y decisiones pendientes. Cada afirmación debe citar identificadores exactos del bloque.

Devuelve:
{{"findings": [{{"dimension": "...", "statement": "...", "source_fragments": ["..."]}}], "uncertainties": [{{"dimension": "...", "description": "...", "source_fragments": ["..."]}}]}}

Bloque de fuentes:
{context}""",
        )
        return payload

    def _compress_summaries(
        self,
        project_name: str,
        domain: str,
        summaries: list[dict[str, Any]],
        progress_callback: Callable[[int, str, str], None] | None = None,
    ) -> list[dict[str, Any]]:
        del project_name, domain
        progress = progress_callback or (lambda _percent, _message, _step: None)
        progress(76, "Uniendo hallazgos equivalentes y sus citas", "consolidating")

        # La consolidación es deliberadamente local y determinista. Pedir a un
        # segundo LLM que resumiera los resúmenes producía salidas extensas que
        # podían truncarse y dejar JSON inválido. Aquí solo se eliminan duplicados
        # textuales normalizados y se unen sus citas; el perfil final sigue siendo
        # construido por el LLM a partir de todos los hallazgos conservados.
        consolidated: dict[str, list[dict[str, Any]]] = {
            "findings": [],
            "uncertainties": [],
        }
        indexes: dict[str, dict[tuple[str, str], int]] = {
            "findings": {},
            "uncertainties": {},
        }
        text_fields = {"findings": "statement", "uncertainties": "description"}

        for summary in summaries:
            if not isinstance(summary, dict):
                continue
            for category, text_field in text_fields.items():
                records = summary.get(category, [])
                if not isinstance(records, list):
                    continue
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    dimension = str(record.get("dimension", "")).strip()
                    text = " ".join(str(record.get(text_field, "")).split())
                    if not dimension or not text:
                        continue
                    normalized = " ".join(
                        re.sub(r"[^a-z0-9áéíóúüñ ]+", " ", text.lower()).split()
                    )
                    key = (dimension, normalized)
                    citations = list(
                        dict.fromkeys(
                            str(value).strip()
                            for value in record.get("source_fragments", [])
                            if str(value).strip()
                        )
                    )
                    existing_index = indexes[category].get(key)
                    if existing_index is not None:
                        existing = consolidated[category][existing_index]
                        existing["source_fragments"] = list(
                            dict.fromkeys(existing["source_fragments"] + citations)
                        )
                        continue
                    indexes[category][key] = len(consolidated[category])
                    consolidated[category].append(
                        {
                            "dimension": dimension,
                            text_field: text,
                            "source_fragments": citations,
                        }
                    )

        progress(
            84,
            (
                f"Consolidados {len(consolidated['findings'])} hallazgos y "
                f"{len(consolidated['uncertainties'])} incertidumbres"
            ),
            "consolidating",
        )
        return [consolidated]

    def _synthesis_prompt(
        self, project_name: str, domain: str, summaries: list[dict[str, Any]], maximum_questions: int
    ) -> str:
        return f"""Proyecto: {project_name}
Dominio declarado: {domain or 'no especificado'}

Construye un perfil provisional para cada una de estas dimensiones: {', '.join(self.DIMENSIONS)}.
- Usa únicamente los resúmenes de evidencia.
- No ocultes contradicciones ni selecciones una alternativa sin confirmación.
- Usa confianza high cuando varias evidencias claras coinciden, medium cuando la evidencia es parcial, low cuando la interpretación es dudosa y missing cuando no hay información.
- Sintetiza cada dimension de forma clara y completa, evitando repetir hallazgos equivalentes. Cada value debe ser menor de 12 000 caracteres.
- Formula hasta {maximum_questions} preguntas solo para información missing o low, contradicciones y decisiones que cambien el comportamiento o la calidad del sistema.
- No preguntes por un dato que ya esté claro. La persona podrá corregir manualmente el perfil provisional.

Devuelve:
{{"profile": [{{"dimension": "...", "value": "...", "source_fragments": ["..."], "confidence": "high|medium|low|missing"}}], "questions": [{{"dimension": "...", "question": "...", "rationale": "...", "source_fragments": ["..."]}}]}}

Resúmenes obtenidos al recorrer el corpus:
{json.dumps(summaries, ensure_ascii=False)}"""

    def _normalize_analysis(
        self, payload: Any, fragments: list[Fragment], maximum_questions: int, batch_count: int
    ) -> dict[str, Any]:
        valid_fragment_ids = {fragment.fragment_id for fragment in fragments}
        profile_records = payload.get("profile", []) if isinstance(payload, dict) else []
        question_records = payload.get("questions", []) if isinstance(payload, dict) else []
        by_dimension = {
            str(item.get("dimension", "")): item
            for item in profile_records
            if isinstance(item, dict) and str(item.get("dimension", "")) in self.DIMENSIONS
        }
        profile: list[dict[str, Any]] = []
        for dimension in self.DIMENSIONS:
            item = by_dimension.get(dimension, {})
            confidence = str(item.get("confidence", "missing")).lower()
            if confidence not in {"high", "medium", "low", "missing"}:
                confidence = "missing"
            value = str(item.get("value", "")).strip()
            if not value:
                confidence = "missing"
            profile.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "source_fragments": self._valid_citations(item, valid_fragment_ids),
                    "confidence": confidence,
                }
            )

        questions: list[dict[str, Any]] = []
        for item in question_records:
            if not isinstance(item, dict) or len(questions) >= maximum_questions:
                continue
            question = str(item.get("question", "")).strip()
            dimension = str(item.get("dimension", "")).strip()
            if not question or dimension not in self.DIMENSIONS:
                continue
            questions.append(
                {
                    "question_key": f"DEF-DYN-{len(questions) + 1:03d}",
                    "dimension": dimension,
                    "question": question,
                    "rationale": str(item.get("rationale", "")).strip(),
                    "required": True,
                    "origin": "dynamic",
                    "evidence": self._valid_citations(item, valid_fragment_ids),
                    "confidence": "pending",
                }
            )

        asked_dimensions = {item["dimension"] for item in questions}
        core_by_dimension = {item["dimension"]: item for item in self.CORE_QUESTIONS}
        for item in profile:
            if len(questions) >= maximum_questions:
                break
            if item["confidence"] not in {"low", "missing"} or item["dimension"] in asked_dimensions:
                continue
            core = core_by_dimension[item["dimension"]]
            questions.append(
                {
                    "question_key": f"DEF-DYN-{len(questions) + 1:03d}",
                    "dimension": item["dimension"],
                    "question": f"¿Cómo debería definirse {core['question'].lower()}?",
                    "rationale": "El corpus no aporta información suficiente para completar esta parte del perfil.",
                    "required": True,
                    "origin": "dynamic",
                    "evidence": item["source_fragments"],
                    "confidence": "pending",
                }
            )
            asked_dimensions.add(item["dimension"])

        return {
            "profile": profile,
            "questions": questions,
            "coverage": {"fragment_count": len(fragments), "batch_count": batch_count},
        }

    @staticmethod
    def _valid_citations(item: dict[str, Any], valid_ids: set[str]) -> list[str]:
        citations = item.get("source_fragments", [])
        if not isinstance(citations, list):
            return []
        return list(dict.fromkeys(str(value) for value in citations if str(value) in valid_ids))


class RevisionAgent:
    """Propone una nueva versión sin sobrescribir el artefacto vigente."""

    def __init__(self, client: LLMClient, retriever: Retriever):
        self.client = client
        self.retriever = retriever

    def propose(self, artifact: dict[str, Any], instruction: str) -> Artifact:
        evidence = self.retriever.retrieve(f"{artifact['description']} {instruction}", top_k=12)
        context = "\n\n".join(f"[{fragment.fragment_id}] {fragment.text}" for fragment, _ in evidence)
        from .llm_schemas import RevisionResponse

        validation_context = {
            "artifact_type": artifact["artifact_type"],
            "valid_citations": [fragment.fragment_id for fragment, _ in evidence],
            "valid_relations": artifact.get("related_artifacts", []),
        }
        validated_completion = getattr(self.client, "complete_json_validated", None)
        common = {
            "system_prompt": (
                "Eres un revisor de requisitos. Propón cambios sustentados, conserva el tipo y el identificador, "
                "y devuelve exclusivamente JSON válido."
            ),
            "user_prompt": f"""Artefacto vigente:
{json.dumps({key: artifact[key] for key in ('artifact_key', 'artifact_type', 'title', 'description', 'priority', 'source_fragments', 'status', 'acceptance_criteria', 'related_artifacts')}, ensure_ascii=False)}

Solicitud del usuario: {instruction}

Evidencia disponible:
{context}

Devuelve {{"artifact": {{"artifact_id": "{artifact['artifact_key']}", "title": "...", "description": "...", "priority": "Alta|Media|Baja", "source_fragments": ["..."], "status": "propuesto|requiere aclaración", "acceptance_criteria": ["..."], "related_artifacts": []}}}}.
No introduzcas información que no esté en la evidencia.""",
        }
        if callable(validated_completion):
            response = validated_completion(
                **common,
                schema=RevisionResponse,
                validation_context=validation_context,
            )
        else:
            response = RevisionResponse.model_validate(
                self.client.complete_json(**common), context=validation_context
            )
        record = response.artifact.model_dump()
        record["artifact_id"] = artifact["artifact_key"]
        return Artifact.from_dict(record, artifact["artifact_type"], 1)
