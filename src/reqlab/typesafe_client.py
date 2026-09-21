from __future__ import annotations

import json
import time
from contextvars import ContextVar
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DecisionClient(Protocol):
    model: str

    @property
    def configured(self) -> bool: ...

    def system_one(
        self,
        state: str | dict[str, Any] | list[Any],
        questions: dict[str, dict[str, Any]],
        timeout: int | None = None,
    ) -> dict[str, Any]: ...

    def get_last_telemetry(self) -> dict[str, Any]: ...


class TypeSafeClientError(RuntimeError):
    """Fallo no recuperable o agotamiento de reintentos de TypeSafe."""


class _RetryableTypeSafeError(RuntimeError):
    def __init__(self, message: str, retry_after: float = 0.0):
        super().__init__(message)
        self.retry_after = retry_after


class TypeSafeDecisionClient:
    """Cliente mínimo para el endpoint de decisiones de Jev.

    Es independiente del cliente generativo de ReqLab porque el contrato de Jev
    recibe ``state`` y preguntas tipadas, no mensajes de Chat Completions. La
    ruta se puede dirigir a OpenRouter o a la API directa de TypeSafe.
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://api.typesafe.ai",
        model: str = "jev-1.13.0",
        endpoint_path: str = "/v1/systemone",
        timeout_seconds: int = 15,
        max_attempts: int = 2,
    ):
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds debe ser mayor que cero.")
        if max_attempts < 1:
            raise ValueError("max_attempts debe ser al menos 1.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        if not endpoint_path.startswith("/"):
            raise ValueError("endpoint_path debe comenzar con '/'.")
        self.endpoint_path = endpoint_path
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self._telemetry: ContextVar[dict[str, Any]] = ContextVar(
            f"typesafe_telemetry_{id(self)}", default={}
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def get_last_telemetry(self) -> dict[str, Any]:
        return dict(self._telemetry.get())

    def _set_telemetry(self, telemetry: dict[str, Any]) -> None:
        self._telemetry.set(dict(telemetry))

    def system_one(
        self,
        state: str | dict[str, Any] | list[Any],
        questions: dict[str, dict[str, Any]],
        timeout: int | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise TypeSafeClientError(
                "La validación semántica está activada, pero TYPESAFE_API_KEY no está configurada."
            )
        if not questions:
            raise ValueError("La solicitud de Jev necesita al menos una pregunta.")

        payload = {"model": self.model, "state": state, "questions": questions}
        attempts = 0
        total_latency_ms = 0.0
        last_error: Exception | None = None

        while attempts < self.max_attempts:
            attempts += 1
            started = time.perf_counter()
            try:
                body = self._request_once(payload, timeout or self.timeout_seconds)
                total_latency_ms += (time.perf_counter() - started) * 1000
                usage = body.get("usage", {}) if isinstance(body, dict) else {}
                self._set_telemetry(
                    {
                        "latency_ms": round(total_latency_ms, 2),
                        "input_tokens": usage.get("input_tokens"),
                        "output_tokens": usage.get("output_tokens"),
                        "attempts": attempts,
                        "requested_model": self.model,
                        "effective_model": body.get("model"),
                    }
                )
                return body
            except _RetryableTypeSafeError as error:
                total_latency_ms += (time.perf_counter() - started) * 1000
                last_error = error
                if attempts < self.max_attempts and error.retry_after > 0:
                    time.sleep(min(error.retry_after, 5.0))
            except (TypeSafeClientError, ValueError) as error:
                total_latency_ms += (time.perf_counter() - started) * 1000
                self._set_telemetry(
                    {
                        "latency_ms": round(total_latency_ms, 2),
                        "attempts": attempts,
                        "failed": True,
                        "requested_model": self.model,
                        "last_error": str(error)[:1000],
                    }
                )
                raise

        message = str(last_error or "fallo de transporte")
        self._set_telemetry(
            {
                "latency_ms": round(total_latency_ms, 2),
                "attempts": attempts,
                "failed": True,
                "requested_model": self.model,
                "last_error": message[:1000],
            }
        )
        raise TypeSafeClientError(
            f"TypeSafe no respondió correctamente tras {attempts} intentos: {message}"
        ) from last_error

    def _request_once(self, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{self.endpoint_path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-OpenRouter-Title": "ReqLab thesis pilot",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            if error.code == 429 or 500 <= error.code <= 599:
                retry_after = self._retry_after_seconds(error.headers.get("Retry-After"))
                raise _RetryableTypeSafeError(
                    f"TypeSafe respondió HTTP {error.code}: {detail}", retry_after
                ) from error
            raise TypeSafeClientError(
                f"TypeSafe respondió HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise _RetryableTypeSafeError(
                f"No se pudo conectar con TypeSafe: {error.reason}"
            ) from error

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as error:
            raise TypeSafeClientError("TypeSafe devolvió una respuesta que no es JSON válido.") from error
        if not isinstance(body, dict):
            raise TypeSafeClientError("TypeSafe devolvió un contrato de respuesta no reconocido.")
        return body

    @staticmethod
    def _retry_after_seconds(value: str | None) -> float:
        if not value:
            return 0.0
        try:
            return max(0.0, float(value))
        except ValueError:
            return 0.0
