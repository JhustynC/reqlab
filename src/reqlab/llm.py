from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DeepSeekClient:
    """Cliente mínimo para la API compatible con Chat Completions de DeepSeek."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"

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
            raise RuntimeError("No se encontró DEEPSEEK_API_KEY en el entorno de ejecución.")
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
            raise RuntimeError(f"DeepSeek respondió HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"No se pudo conectar con DeepSeek: {error.reason}") from error
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("La respuesta de DeepSeek no contiene contenido utilizable.") from error
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(content).strip(), flags=re.IGNORECASE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise RuntimeError("DeepSeek devolvió una respuesta que no es JSON válido.") from error

