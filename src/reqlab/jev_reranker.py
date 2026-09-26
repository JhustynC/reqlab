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
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
    ):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self.max_attempts = max(1, max_attempts)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
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
        decisions: dict[str, dict[str, float]] = {}
        request_audit: list[dict[str, Any]] = []
        input_tokens = output_tokens = requests = 0
        total_cost = 0.0
        cost_reported = False
        try:
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
                request_started = time.perf_counter()
                body = self._decide({"model": self.model, "state": state, "questions": questions})
                request_latency = round((time.perf_counter() - request_started) * 1000, 2)
                requests += 1
                answers = body.get("answers")
                if not isinstance(answers, dict) or set(answers) != set(questions):
                    raise RuntimeError("Jev devolvió un conjunto incompleto de decisiones de reranking.")
                for index, (fragment, _) in enumerate(batch):
                    relevance = self._probability(answers[f"relevant_{index}"])
                    evidence = self._probability(answers[f"evidence_{index}"])
                    combined = (relevance + evidence) / 2
                    scores[fragment.fragment_id] = combined
                    decisions[fragment.fragment_id] = {
                        "topical_relevance": relevance,
                        "useful_evidence": evidence,
                        "combined_score": combined,
                    }
                usage = body.get("usage") or {}
                batch_input = batch_output = 0
                batch_cost: float | None = None
                if isinstance(usage, dict):
                    batch_input = self._token_count(usage.get("input_tokens"))
                    batch_output = self._token_count(usage.get("output_tokens"))
                    input_tokens += batch_input
                    output_tokens += batch_output
                    raw_cost = usage.get("cost")
                    if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool):
                        batch_cost = max(0.0, float(raw_cost))
                        total_cost += batch_cost
                        cost_reported = True
                request_audit.append(
                    {
                        "batch": (offset // self.batch_size) + 1,
                        "candidate_ids": [fragment.fragment_id for fragment, _ in batch],
                        "request_id": body.get("id"),
                        "requested_model": self.model,
                        "served_model": body.get("model"),
                        "provider": body.get("provider"),
                        "attempts": int(body.get("_reqlab_request_attempts") or 1),
                        "input_tokens": batch_input,
                        "output_tokens": batch_output,
                        "cost": batch_cost,
                        "latency_ms": request_latency,
                    }
                )
        except Exception as error:
            self._telemetry.set(
                {
                    "status": "failed",
                    "requested_model": self.model,
                    "requests": requests,
                    "candidate_count": len(candidates),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "cost": total_cost if cost_reported else None,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "request_audit": request_audit,
                    "error": str(error),
                }
            )
            raise
        # El orden RRF original resuelve empates; ningún candidato se descarta
        # antes de seleccionar top_k, incluidas posibles contradicciones.
        ranked = sorted(
            enumerate(candidates),
            key=lambda item: (-scores[item[1][0].fragment_id], item[0]),
        )
        selected = ranked[:top_k]
        final_positions = {
            fragment.fragment_id: position
            for position, (_, (fragment, _)) in enumerate(ranked, start=1)
        }
        selected_ids = {fragment.fragment_id for _, (fragment, _) in selected}
        candidate_audit = [
            {
                "fragment_id": fragment.fragment_id,
                "original_rrf_rank": original_rank,
                "original_rrf_score": round(float(rrf_score), 8),
                **decisions[fragment.fragment_id],
                "final_rank": final_positions[fragment.fragment_id],
                "selected": fragment.fragment_id in selected_ids,
            }
            for original_rank, (fragment, rrf_score) in enumerate(candidates, start=1)
        ]
        self._telemetry.set(
            {
                "status": "completed",
                "requested_model": self.model,
                "served_models": list(
                    dict.fromkeys(
                        str(item["served_model"])
                        for item in request_audit
                        if item.get("served_model")
                    )
                ),
                "requests": requests,
                "candidate_count": len(candidates),
                "selected_count": len(selected),
                "top_k": top_k,
                "score_formula": "(topical_relevance + useful_evidence) / 2",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost": total_cost if cost_reported else None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "request_audit": request_audit,
                "candidates": candidate_audit,
            }
        )
        return [(fragment, scores[fragment.fragment_id]) for _, (fragment, _) in selected]

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
        body: Any = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    body = json.load(response)
                break
            except HTTPError as error:
                retryable = error.code == 429 or 500 <= error.code < 600
                if retryable and attempt < self.max_attempts:
                    retry_after = error.headers.get("Retry-After") if error.headers else None
                    try:
                        delay = float(retry_after) if retry_after else self.retry_backoff_seconds * attempt
                    except (TypeError, ValueError):
                        delay = self.retry_backoff_seconds * attempt
                    time.sleep(max(0.0, min(delay, 5.0)))
                    continue
                detail = error.read().decode("utf-8", errors="replace")[:350]
                raise RuntimeError(f"OpenRouter respondió HTTP {error.code}: {detail}") from error
            except URLError as error:
                if attempt < self.max_attempts:
                    time.sleep(min(self.retry_backoff_seconds * attempt, 5.0))
                    continue
                raise RuntimeError(f"No se pudo conectar con Jev: {error.reason}") from error
            except (ValueError, UnicodeError) as error:
                raise RuntimeError("OpenRouter devolvió una respuesta inválida.") from error
        if not isinstance(body, dict):
            raise RuntimeError("OpenRouter devolvió un contrato de decisiones inválido.")
        body["_reqlab_request_attempts"] = attempt
        return body
