from __future__ import annotations

import json
import os
import re
import time
from contextvars import ContextVar
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    model: str

    @property
    def configured(self) -> bool: ...

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        timeout: int = 120,
    ) -> dict[str, Any] | list[Any]: ...

    def get_last_telemetry(self) -> dict[str, Any]: ...


class OpenAICompatibleClient:
    """Cliente mínimo para APIs compatibles con OpenAI Chat Completions."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = (
            base_url
            or os.getenv("LLM_BASE_URL")
            or os.getenv("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com"
        ).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
        self.max_retries = max_retries
        self._telemetry: ContextVar[dict[str, Any]] = ContextVar(
            f"llm_telemetry_{id(self)}", default={}
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def get_last_telemetry(self) -> dict[str, Any]:
        return dict(self._telemetry.get())

    def reset_telemetry(self) -> None:
        self._telemetry.set({})

    def _set_telemetry(self, telemetry: dict[str, Any]) -> None:
        self._telemetry.set(dict(telemetry))

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        timeout: int = 120,
    ) -> dict[str, Any] | list[Any]:
        if not self.api_key:
            raise RuntimeError(
                "No se encontró LLM_API_KEY ni DEEPSEEK_API_KEY en el entorno de ejecución."
            )
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        self._set_telemetry({})
        start_time = time.perf_counter()
        try:
            with urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            self._set_telemetry({
                "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                "attempts": 1,
                "failed": True,
            })
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"El LLM respondió HTTP {error.code}: {detail}") from error
        except URLError as error:
            self._set_telemetry({
                "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                "attempts": 1,
                "failed": True,
            })
            raise RuntimeError(f"No se pudo conectar con el LLM: {error.reason}") from error
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        usage = body.get("usage", {}) if isinstance(body, dict) else {}
        total_tokens = usage.get("total_tokens")
        if total_tokens is None and usage.get("prompt_tokens") is not None and usage.get("completion_tokens") is not None:
            total_tokens = usage["prompt_tokens"] + usage["completion_tokens"]
        self._set_telemetry({
            "latency_ms": elapsed_ms,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": total_tokens,
            "attempts": 1,
        })

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("La respuesta del LLM no contiene contenido utilizable.") from error
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(content).strip(), flags=re.IGNORECASE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise RuntimeError("El LLM devolvió una respuesta que no es JSON válido.") from error

    def complete_json_validated(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
        temperature: float = 0.1,
        timeout: int = 120,
        max_retries: int | None = None,
        validation_context: dict[str, Any] | None = None,
    ) -> T:
        attempts = max_retries if max_retries is not None else self.max_retries
        last_error: Exception | None = None
        total_latency_ms = 0.0
        total_tokens_accum = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if attempts < 1:
            raise ValueError("max_retries debe ser al menos 1.")

        for attempt in range(1, attempts + 1):
            try:
                payload = self.complete_json(system_prompt, user_prompt, temperature, timeout)
                current = self.get_last_telemetry()
                total_latency_ms += current.get("latency_ms", 0.0)
                for key in total_tokens_accum:
                    value = current.get(key)
                    if value is not None:
                        total_tokens_accum[key] += value
                validated = schema.model_validate(payload, context=validation_context)
                self._set_telemetry({
                    "latency_ms": round(total_latency_ms, 2),
                    "prompt_tokens": total_tokens_accum["prompt_tokens"] or None,
                    "completion_tokens": total_tokens_accum["completion_tokens"] or None,
                    "total_tokens": total_tokens_accum["total_tokens"] or None,
                    "attempts": attempt,
                })
                return validated
            except (ValidationError, RuntimeError, ValueError) as error:
                last_error = error
                # Los fallos de transporte/JSON ya traen la telemetría del intento.
                # Los fallos de validación ya fueron acumulados en el bloque anterior.
                if not isinstance(error, ValidationError):
                    current = self.get_last_telemetry()
                    total_latency_ms += current.get("latency_ms", 0.0)
                    for key in total_tokens_accum:
                        value = current.get(key)
                        if value is not None:
                            total_tokens_accum[key] += value
                if attempt >= attempts:
                    break
                user_prompt = (
                    f"{user_prompt}\n\n"
                    f"La respuesta anterior no cumplió el esquema esperado ({error}). "
                    "Devuelve exclusivamente JSON válido que cumpla el contrato solicitado."
                )

        self._set_telemetry({
            "latency_ms": round(total_latency_ms, 2),
            "prompt_tokens": total_tokens_accum["prompt_tokens"] or None,
            "completion_tokens": total_tokens_accum["completion_tokens"] or None,
            "total_tokens": total_tokens_accum["total_tokens"] or None,
            "attempts": attempts,
            "failed": True,
            "last_error": self._error_summary(last_error),
        })
        detail = self._error_summary(last_error)
        raise RuntimeError(
            f"El LLM no devolvió una respuesta válida tras {attempts} intentos. "
            f"Último rechazo: {detail}"
        ) from last_error

    @staticmethod
    def _error_summary(error: Exception | None) -> str:
        if error is None:
            return "motivo no disponible"
        if isinstance(error, ValidationError):
            details = error.errors(include_url=False, include_input=False)
            return "; ".join(
                f"{'.'.join(str(part) for part in item.get('loc', ()))}: {item.get('msg', 'valor inválido')}"
                for item in details[:8]
            )[:1200]
        return re.sub(r"\s+", " ", str(error)).strip()[:1200]



# Alias retrocompatible con la configuración y el código existente.
DeepSeekClient = OpenAICompatibleClient
