from __future__ import annotations

import json
import os
import re
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

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

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
        try:
            with urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"El LLM respondió HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"No se pudo conectar con el LLM: {error.reason}") from error
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
    ) -> T:
        attempts = max_retries if max_retries is not None else self.max_retries
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                payload = self.complete_json(system_prompt, user_prompt, temperature, timeout)
                return schema.model_validate(payload)
            except (ValidationError, RuntimeError, ValueError) as error:
                last_error = error
                if attempt >= attempts:
                    break
                user_prompt = (
                    f"{user_prompt}\n\n"
                    f"La respuesta anterior no cumplió el esquema esperado ({error}). "
                    "Devuelve exclusivamente JSON válido que cumpla el contrato solicitado."
                )
        raise RuntimeError(f"El LLM no devolvió una respuesta válida tras {attempts} intentos.") from last_error


# Alias retrocompatible con la configuración y el código existente.
DeepSeekClient = OpenAICompatibleClient
