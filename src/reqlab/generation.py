from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import Artifact, Fragment
from .retrieval import TfidfRetrievalAgent

TASKS = {
    "RF": "requisitos funcionales verificables que describan capacidades del sistema",
    "RNF": "requisitos no funcionales verificables sobre atributos de calidad, seguridad, rendimiento, compatibilidad, usabilidad, retención o trazabilidad; no describas funciones de negocio",
    "HU": "historias de usuario con el formato 'Como [rol], quiero [objetivo], para [beneficio]' y criterios de aceptación",
}


class DeepSeekGenerationAgent:
    """Genera artefactos estructurados a partir del contexto recuperado por RAG."""

    def __init__(
        self,
        retriever: TfidfRetrievalAgent,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        system_name: str = "el sistema bajo análisis",
        domain: str = "el dominio descrito por el corpus",
    ):
        self.retriever = retriever
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
        self.system_name = system_name
        self.domain = domain

    def generate(self, artifact_type: str, limit: int = 18) -> tuple[list[Artifact], list[tuple[Fragment, float]]]:
        if artifact_type not in TASKS:
            raise ValueError(f"Tipo de artefacto no soportado: {artifact_type}")
        if not self.api_key:
            raise RuntimeError("No se encontró DEEPSEEK_API_KEY. Añádala solo a un archivo .env local o a la variable de entorno.")
        query = f"{self.system_name} {self.domain} {TASKS[artifact_type]}"
        evidence = self.retriever.retrieve(query, top_k=16)
        prompt = self._build_prompt(artifact_type, evidence, limit)
        response = self._request(prompt)
        records = self._parse_json(response)
        artifacts = [Artifact.from_dict(record, artifact_type, index + 1) for index, record in enumerate(records)]
        return artifacts, evidence

    def _build_prompt(self, artifact_type: str, evidence: list[tuple[Fragment, float]], limit: int) -> str:
        context = "\n\n".join(f"{fragment.fragment_id} | {fragment.heading}\n{fragment.text}" for fragment, _ in evidence)
        schema = {
            "artifact_id": f"{artifact_type}-001",
            "title": "título breve",
            "description": "texto del requisito o historia",
            "priority": "Alta|Media|Baja",
            "source_fragments": ["SRC-01-F02"],
            "status": "propuesto|requiere aclaración",
            "acceptance_criteria": ["solo obligatorio en HU"],
        }
        return f"""Eres el agente generador de requisitos para el sistema '{self.system_name}', cuyo dominio es '{self.domain}'. Genera como máximo {limit} {TASKS[artifact_type]}.

Reglas obligatorias:
1. Usa exclusivamente el contexto entregado; no inventes actores, reglas ni métricas.
2. Cada elemento debe incluir uno o más source_fragments con IDs exactos del contexto.
3. Si una regla es contradictoria o incompleta, usa status 'requiere aclaración' y describe la incertidumbre sin resolverla.
4. No repitas requisitos equivalentes ni introduzcas alcance que no aparezca en el corpus.
5. Devuelve SOLO un objeto JSON válido con esta forma: {{"artifacts": [ ... ]}}. No uses Markdown ni explicación.

Esquema de cada elemento: {json.dumps(schema, ensure_ascii=False)}

Contexto recuperado:
{context}"""

    def _request(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Responde en español y respeta exactamente el formato solicitado."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"DeepSeek respondió HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"No se pudo conectar con DeepSeek: {error.reason}") from error
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("La respuesta de DeepSeek no contiene contenido de generación.") from error

    @staticmethod
    def _parse_json(content: str) -> list[dict]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        data = json.loads(cleaned)
        if isinstance(data, dict):
            for key in ("artifacts", "items", "requirements", "historias_usuario"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise RuntimeError("La respuesta no es un arreglo JSON de artefactos.")
        return data


def load_local_env(project_dir: str | Path = ".") -> None:
    """Carga pares simples KEY=VALUE desde .env sin imprimir ningún valor."""
    path = Path(project_dir) / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
