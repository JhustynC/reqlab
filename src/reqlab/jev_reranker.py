from __future__ import annotations

import json
import math
import time
from contextvars import ContextVar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import Fragment


class JevReranker:
    """Reordena candidatos RRF con decisiones Noul de Jev vía OpenRouter."""

    def __init__(
        self,
        api_key: str | None,
        model: str = "typesafe/jev-1.13",
        endpoint: str = "https://openrouter.ai/api/alpha/decisions",
        timeout_seconds: int = 25,
        batch_size: int = 8,
    ):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self._telemetry: ContextVar[dict[str, Any]] = ContextVar(
            f"jev_rerank_{id(self)}", default={}
        )

    def get_last_telemetry(self) -> dict[str, Any]:
        return dict(self._telemetry.get())

    def reset_telemetry(self) -> None:
        self._telemetry.set({})

    def rerank(
        self,
        query: str,
        candidates: list[tuple[Fragment, float]],
        top_k: int,
    ) -> list[tuple[Fragment, float]]:
        if not candidates:
            return []
        if not self.api_key:
            raise RuntimeError("Jev requiere OPENROUTER_API_KEY en .env.")
        self._telemetry.set({})
        started = time.perf_counter()
        scores: dict[str, float] = {}
        input_tokens = output_tokens = 0
        requests = 0
        for offset in range(0, len(candidates), self.batch_size):
            batch = candidates[offset : offset + self.batch_size]
            state = {
                "query": query,
                "passages": [
                    {"id": fragment.fragment_id, "heading": fragment.heading, "text": fragment.text}
                    for fragment, _ in batch
                ],
            }
            questions: dict[str, dict[str, str]] = {}
            for index, (fragment, _) in enumerate(batch):
                passage = f"passages[{index}] (id={fragment.fragment_id})"
                questions[f"relevant_{index}"] = {
                    "type": "noul",
                    "instructions": f"¿El pasaje {passage} trata el tema de query?",
                }
                questions[f"evidence_{index}"] = {
                    "type": "noul",
                    "instructions": (
                        f"¿El pasaje {passage} aporta un hecho, regla, restricción o necesidad "
                        "concreta útil para la tarea expresada en query, incluso si contradice "
                        "otra fuente?"
                    ),
                }
            body = self._decide({"model": self.model, "state": state, "questions": questions})
            requests += 1
            answers = body.get("answers")
            if not isinstance(answers, dict) or set(answers) != set(questions):
                raise RuntimeError("Jev devolvió un conjunto incompleto de decisiones de reranking.")
            for index, (fragment, _) in enumerate(batch):
                relevance = self._probability(answers[f"relevant_{index}"])
                evidence = self._probability(answers[f"evidence_{index}"])
                scores[fragment.fragment_id] = (relevance + evidence) / 2
            usage = body.get("usage") or {}
            if isinstance(usage, dict):
                input_tokens += self._token_count(usage.get("input_tokens"))
                output_tokens += self._token_count(usage.get("output_tokens"))
            self._telemetry.set({
                "model": self.model,
                "requests": requests,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            })
        self._telemetry.set({
            "model": self.model,
            "requests": requests,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        })
        # El orden RRF original resuelve empates; ningún candidato se descarta
        # antes de seleccionar top_k, incluidas posibles contradicciones.
        ranked = sorted(
            enumerate(candidates),
            key=lambda item: (-scores[item[1][0].fragment_id], item[0]),
        )
        return [(fragment, scores[fragment.fragment_id]) for _, (fragment, _) in ranked[:top_k]]

    @staticmethod
    def _probability(answer: Any) -> float:
        value = answer.get("noul") if isinstance(answer, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError("Jev devolvió una probabilidad inválida.")
        value = float(value)
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise RuntimeError("Jev devolvió una probabilidad fuera de rango.")
        return value

    @staticmethod
    def _token_count(value: Any) -> int:
        return max(0, int(value)) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0

    def _decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.load(response)
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:350]
            raise RuntimeError(f"OpenRouter respondió HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"No se pudo conectar con Jev: {error.reason}") from error
        except (ValueError, UnicodeError) as error:
            raise RuntimeError("OpenRouter devolvió una respuesta inválida.") from error
        if not isinstance(body, dict):
            raise RuntimeError("OpenRouter devolvió un contrato de decisiones inválido.")
        return body
