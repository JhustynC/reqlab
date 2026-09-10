from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from .llm import DeepSeekClient
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
    ),
}


class SpecializedGenerationAgent:
    """Agente LLM con identidad, responsabilidad y contrato de salida explícitos."""

    def __init__(
        self,
        contract: AgentContract,
        retriever: Retriever,
        client: DeepSeekClient,
        project_name: str,
        domain: str,
    ):
        self.contract = contract
        self.retriever = retriever
        self.client = client
        self.project_name = project_name
        self.domain = domain or "dominio descrito por las fuentes"

    def generate(self, limit: int = 15) -> tuple[list[Artifact], list[tuple[Fragment, float]]]:
        query = f"{self.project_name} {self.domain} {self.contract.task}"
        evidence = self.retriever.retrieve(query, top_k=24)
        if not evidence:
            raise RuntimeError(f"{self.contract.agent_id} no recuperó evidencia suficiente para generar artefactos.")
        payload = self.client.complete_json(
            system_prompt=(
                f"Actúas como {self.contract.role}. Trabajas únicamente con evidencia citada. "
                "Responde en español y devuelve exclusivamente JSON válido."
            ),
            user_prompt=self._prompt(evidence, limit),
        )
        records = payload.get("artifacts", []) if isinstance(payload, dict) else payload
        if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
            raise RuntimeError(f"{self.contract.agent_id} no devolvió la colección 'artifacts' esperada.")
        artifacts = [
            Artifact.from_dict(self._normalize_record(item, index), self.contract.artifact_type, index)
            for index, item in enumerate(records[:limit], start=1)
        ]
        return artifacts, evidence

    def _normalize_record(self, record: dict[str, Any], index: int) -> dict[str, Any]:
        normalized = dict(record)
        normalized["artifact_id"] = f"{self.contract.artifact_type}-{index:03d}"
        return normalized

    def _prompt(self, evidence: list[tuple[Fragment, float]], limit: int) -> str:
        context = "\n\n".join(
            f"[{fragment.fragment_id}] {fragment.heading}\n{fragment.text}" for fragment, _ in evidence
        )
        schema = {
            "artifact_id": f"{self.contract.artifact_type}-001",
            "title": "Título breve",
            "description": "Enunciado completo",
            "priority": "Alta|Media|Baja",
            "source_fragments": ["identificador exacto de un fragmento"],
            "status": "propuesto|requiere aclaración",
            "acceptance_criteria": ["Criterio verificable; obligatorio para HU"],
        }
        rules = "\n".join(f"- {rule}" for rule in self.contract.quality_rules)
        return f"""Proyecto: {self.project_name}
Dominio: {self.domain}
Tarea exclusiva del agente: {self.contract.task}

Reglas especializadas:
{rules}

Reglas comunes:
- Genera como máximo {limit} artefactos sin duplicados.
- Usa solamente la evidencia proporcionada.
- Cada artefacto debe citar uno o más identificadores exactos presentes en el contexto.
- Si falta información, conserva la incertidumbre y usa el estado 'requiere aclaración'.
- No resuelvas contradicciones mediante suposiciones.
- Devuelve {{"artifacts": [...]}} usando este esquema: {json.dumps(schema, ensure_ascii=False)}

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

    def __init__(self, client: DeepSeekClient, batch_character_limit: int = 18000):
        self.client = client
        self.batch_character_limit = batch_character_limit

    def analyze(
        self, project_name: str, domain: str, fragments: list[Fragment], maximum_questions: int = 10
    ) -> dict[str, Any]:
        if not fragments:
            raise ValueError("No hay fragmentos para analizar.")
        batches = self._batches(fragments)
        summaries = [self._analyze_batch(project_name, domain, batch) for batch in batches]
        summaries = self._compress_summaries(project_name, domain, summaries)
        payload = self.client.complete_json(
            system_prompt=(
                "Eres un analista de requisitos en una etapa de elicitación. Construye una interpretación "
                "provisional sustentada, conserva las contradicciones y no generes RF, RNF ni historias de usuario. "
                "Devuelve exclusivamente JSON válido."
            ),
            user_prompt=self._synthesis_prompt(project_name, domain, summaries, maximum_questions),
        )
        return self._normalize_analysis(payload, fragments, maximum_questions, len(batches))

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
        return self.client.complete_json(
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

    def _compress_summaries(
        self, project_name: str, domain: str, summaries: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        while len(json.dumps(summaries, ensure_ascii=False)) > 32000 and len(summaries) > 1:
            groups: list[list[dict[str, Any]]] = []
            current: list[dict[str, Any]] = []
            size = 0
            for summary in summaries:
                rendered = json.dumps(summary, ensure_ascii=False)
                if current and size + len(rendered) > 18000:
                    groups.append(current)
                    current, size = [], 0
                current.append(summary)
                size += len(rendered)
            if current:
                groups.append(current)
            summaries = [
                self.client.complete_json(
                    system_prompt=(
                        "Fusiona resúmenes de evidencia sin perder citas, ausencias ni contradicciones. "
                        "No generes requisitos y devuelve exclusivamente JSON válido."
                    ),
                    user_prompt=f"""Proyecto: {project_name}
Dominio: {domain or 'no especificado'}
Devuelve el mismo esquema de findings y uncertainties. Une duplicados, pero conserva posiciones incompatibles y todos sus identificadores de fuente.

Resúmenes:
{json.dumps(group, ensure_ascii=False)}""",
                )
                for group in groups
            ]
        return summaries

    def _synthesis_prompt(
        self, project_name: str, domain: str, summaries: list[dict[str, Any]], maximum_questions: int
    ) -> str:
        return f"""Proyecto: {project_name}
Dominio declarado: {domain or 'no especificado'}

Construye un perfil provisional para cada una de estas dimensiones: {', '.join(self.DIMENSIONS)}.
- Usa únicamente los resúmenes de evidencia.
- No ocultes contradicciones ni selecciones una alternativa sin confirmación.
- Usa confianza high cuando varias evidencias claras coinciden, medium cuando la evidencia es parcial, low cuando la interpretación es dudosa y missing cuando no hay información.
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

    def __init__(self, client: DeepSeekClient, retriever: Retriever):
        self.client = client
        self.retriever = retriever

    def propose(self, artifact: dict[str, Any], instruction: str) -> Artifact:
        evidence = self.retriever.retrieve(f"{artifact['description']} {instruction}", top_k=12)
        context = "\n\n".join(f"[{fragment.fragment_id}] {fragment.text}" for fragment, _ in evidence)
        payload = self.client.complete_json(
            system_prompt=(
                "Eres un revisor de requisitos. Propón cambios sustentados, conserva el tipo y el identificador, "
                "y devuelve exclusivamente JSON válido."
            ),
            user_prompt=f"""Artefacto vigente:
{json.dumps({key: artifact[key] for key in ('artifact_key', 'artifact_type', 'title', 'description', 'priority', 'source_fragments', 'status', 'acceptance_criteria')}, ensure_ascii=False)}

Solicitud del usuario: {instruction}

Evidencia disponible:
{context}

Devuelve {{"artifact": {{"artifact_id": "{artifact['artifact_key']}", "title": "...", "description": "...", "priority": "Alta|Media|Baja", "source_fragments": ["..."], "status": "propuesto|requiere aclaración", "acceptance_criteria": ["..."]}}}}.
No introduzcas información que no esté en la evidencia.""",
        )
        record = payload.get("artifact") if isinstance(payload, dict) else None
        if not isinstance(record, dict):
            raise RuntimeError("El agente de revisión no devolvió la propuesta esperada.")
        record["artifact_id"] = artifact["artifact_key"]
        return Artifact.from_dict(record, artifact["artifact_type"], 1)
