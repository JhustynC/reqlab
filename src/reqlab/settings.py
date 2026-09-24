from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, fallback: str = "") -> str:
    return os.getenv(name, fallback).strip()


def _env_float(name: str, fallback: float) -> float:
    raw = _env(name)
    return float(raw) if raw else fallback


def _env_int(name: str, fallback: int) -> int:
    raw = _env(name)
    return int(raw) if raw else fallback


def _env_bool(name: str, fallback: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return fallback
    return raw in {"1", "true", "yes", "on"}


def _env_optional_float(name: str) -> float | None:
    raw = _env(name)
    return float(raw) if raw else None


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cors_origins: tuple[str, ...]
    max_upload_bytes: int
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str
    llm_max_retries: int
    llm_thinking_enabled: bool
    llm_max_tokens: int
    definition_batch_character_limit: int
    definition_max_workers: int
    definition_max_questions: int
    embedding_model: str
    embedding_query_prefix: str
    embedding_passage_prefix: str
    reranker_enabled: bool
    reranker_model: str
    rrf_lexical_weight: float
    rrf_semantic_weight: float
    retrieval_top_k: int
    chunk_size: int
    chunk_overlap: int
    duplicate_threshold: float
    cross_type_duplicate_threshold: float
    prompt_version: str
    reranker_provider: str = "local"
    jev_model: str = "typesafe/jev-1.13"
    semantic_validation_enabled: bool = False
    semantic_validation_mode: str = "shadow"
    typesafe_api_key: str | None = None
    typesafe_base_url: str = "https://api.typesafe.ai"
    typesafe_model: str = "jev-1.13.0"
    typesafe_endpoint_path: str = "/v1/systemone"
    semantic_timeout_seconds: int = 15
    semantic_max_attempts: int = 2
    semantic_prompt_version: str = "jev-evidence-v1"
    semantic_confidence_threshold: float | None = None

    def __post_init__(self) -> None:
        if self.max_upload_bytes < 1:
            raise ValueError("MAX_UPLOAD_BYTES debe ser mayor que cero.")
        if self.llm_max_retries < 1:
            raise ValueError("LLM_MAX_RETRIES debe ser al menos 1.")
        if self.llm_max_tokens < 1:
            raise ValueError("LLM_MAX_TOKENS debe ser al menos 1.")
        if self.definition_batch_character_limit < 3000:
            raise ValueError("DEFINITION_BATCH_CHARACTER_LIMIT debe ser al menos 3000.")
        if self.definition_max_workers < 1:
            raise ValueError("DEFINITION_MAX_WORKERS debe ser al menos 1.")
        if self.definition_max_questions < 1:
            raise ValueError("DEFINITION_MAX_QUESTIONS debe ser al menos 1.")
        if self.retrieval_top_k < 1:
            raise ValueError("RETRIEVAL_TOP_K debe ser mayor que cero.")
        if self.reranker_provider not in {"local", "jev"}:
            raise ValueError("RERANKER_PROVIDER debe ser local o jev.")
        if self.chunk_size < 300:
            raise ValueError("CHUNK_SIZE debe ser al menos 300 caracteres.")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP debe estar entre 0 y CHUNK_SIZE - 1.")
        if self.rrf_lexical_weight < 0 or self.rrf_semantic_weight < 0:
            raise ValueError("Los pesos RRF no pueden ser negativos.")
        if self.rrf_lexical_weight + self.rrf_semantic_weight <= 0:
            raise ValueError("Al menos un peso RRF debe ser mayor que cero.")
        if not 0 < self.duplicate_threshold <= 1:
            raise ValueError("DUPLICATE_THRESHOLD debe estar en el intervalo (0, 1].")
        if not 0 < self.cross_type_duplicate_threshold <= 1:
            raise ValueError("CROSS_TYPE_DUPLICATE_THRESHOLD debe estar en el intervalo (0, 1].")
        if self.semantic_validation_mode != "shadow":
            raise ValueError("SEMANTIC_VALIDATION_MODE solo admite 'shadow' durante el piloto.")
        if self.semantic_timeout_seconds < 1:
            raise ValueError("SEMANTIC_TIMEOUT_SECONDS debe ser mayor que cero.")
        if self.semantic_max_attempts < 1:
            raise ValueError("SEMANTIC_MAX_ATTEMPTS debe ser al menos 1.")
        if not self.typesafe_endpoint_path.startswith("/"):
            raise ValueError("TYPESAFE_ENDPOINT_PATH debe comenzar con '/'.")
        if (
            self.semantic_confidence_threshold is not None
            and not 0 <= self.semantic_confidence_threshold <= 1
        ):
            raise ValueError("SEMANTIC_CONFIDENCE_THRESHOLD debe estar entre 0 y 1.")

    def experimental_snapshot(self) -> dict[str, object]:
        """Configuración suficiente para interpretar y reproducir una ejecución."""
        return {
            "llm": {
                "model": self.llm_model,
                "base_url": self.llm_base_url,
                "thinking_mode": "enabled" if self.llm_thinking_enabled else "disabled",
                "max_tokens": self.llm_max_tokens,
            },
            "embedding": {
                "model": self.embedding_model,
                "query_prefix": self.embedding_query_prefix,
                "passage_prefix": self.embedding_passage_prefix,
            },
            "reranker": {
                "enabled": self.reranker_enabled,
                "provider": self.reranker_provider,
                "model": self.jev_model if self.reranker_provider == "jev" else self.reranker_model,
            },
            "retrieval": {
                "method": "hybrid_rrf",
                "top_k": self.retrieval_top_k,
                "lexical_weight": self.rrf_lexical_weight,
                "semantic_weight": self.rrf_semantic_weight,
            },
            "segmentation": {"chunk_size": self.chunk_size, "overlap": self.chunk_overlap},
            "definition": {
                "batch_character_limit": self.definition_batch_character_limit,
                "max_workers": self.definition_max_workers,
                "max_questions": self.definition_max_questions,
            },
            "validation": {
                "duplicate_threshold": self.duplicate_threshold,
                "cross_type_duplicate_threshold": self.cross_type_duplicate_threshold,
            },
            "semantic_validation": {
                "enabled": self.semantic_validation_enabled,
                "mode": self.semantic_validation_mode,
                "provider": "typesafe",
                "model": self.typesafe_model,
                "base_url": self.typesafe_base_url,
                "endpoint_path": self.typesafe_endpoint_path,
                "timeout_seconds": self.semantic_timeout_seconds,
                "max_attempts": self.semantic_max_attempts,
                "prompt_version": self.semantic_prompt_version,
                "confidence_threshold": self.semantic_confidence_threshold,
            },
            "prompt_version": self.prompt_version,
        }

    @classmethod
    def from_environment(cls) -> "Settings":
        data_dir = Path(_env("DATA_DIR") or str(Path.cwd() / "data"))
        origins = tuple(
            value.strip()
            for value in _env("CORS_ORIGINS", "http://localhost:4200,http://localhost:8080").split(",")
            if value.strip()
        )
        llm_api_key = _env("LLM_API_KEY") or _env("DEEPSEEK_API_KEY") or None
        llm_base_url = (
            _env("LLM_BASE_URL")
            or _env("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com"
        ).rstrip("/")
        llm_model = _env("LLM_MODEL") or _env("DEEPSEEK_MODEL") or "deepseek-flash"
        embedding_model = _env(
            "EMBEDDING_MODEL",
            "intfloat/multilingual-e5-base",
        )
        query_prefix = _env("EMBEDDING_QUERY_PREFIX")
        passage_prefix = _env("EMBEDDING_PASSAGE_PREFIX")
        if "e5" in embedding_model.lower():
            query_prefix = query_prefix or "query: "
            passage_prefix = passage_prefix or "passage: "
        return cls(
            data_dir=data_dir,
            cors_origins=origins,
            max_upload_bytes=_env_int("MAX_UPLOAD_BYTES", 20 * 1024 * 1024),
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_max_retries=_env_int("LLM_MAX_RETRIES", 3),
            llm_thinking_enabled=_env_bool("LLM_THINKING_ENABLED", False),
            llm_max_tokens=_env_int("LLM_MAX_TOKENS", 12000),
            definition_batch_character_limit=_env_int(
                "DEFINITION_BATCH_CHARACTER_LIMIT", 18000
            ),
            definition_max_workers=_env_int("DEFINITION_MAX_WORKERS", 3),
            definition_max_questions=_env_int("DEFINITION_MAX_QUESTIONS", 10),
            embedding_model=embedding_model,
            embedding_query_prefix=query_prefix,
            embedding_passage_prefix=passage_prefix,
            reranker_enabled=_env_bool("RERANKER_ENABLED", False),
            reranker_provider=_env("RERANKER_PROVIDER", "local").lower(),
            jev_model=_env("JEV_MODEL", "typesafe/jev-1.13"),
            reranker_model=_env(
                "RERANKER_MODEL",
                "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
            ),
            rrf_lexical_weight=_env_float("RRF_LEXICAL_WEIGHT", 0.45),
            rrf_semantic_weight=_env_float("RRF_SEMANTIC_WEIGHT", 0.55),
            retrieval_top_k=_env_int("RETRIEVAL_TOP_K", 12),
            chunk_size=_env_int("CHUNK_SIZE", 1200),
            chunk_overlap=_env_int("CHUNK_OVERLAP", 180),
            duplicate_threshold=_env_float("DUPLICATE_THRESHOLD", 0.72),
            cross_type_duplicate_threshold=_env_float("CROSS_TYPE_DUPLICATE_THRESHOLD", 0.55),
            prompt_version=_env("PROMPT_VERSION", "reqlab-v2"),
            semantic_validation_enabled=_env_bool("SEMANTIC_VALIDATION_ENABLED", False),
            semantic_validation_mode=_env("SEMANTIC_VALIDATION_MODE", "shadow").lower(),
            typesafe_api_key=_env("TYPESAFE_API_KEY") or _env("OPENROUTER_API_KEY") or None,
            # El acceso disponible para este piloto usa la ruta de OpenRouter.
            # Para la API directa de TypeSafe se pueden sobreescribir los tres
            # valores con api.typesafe.ai, jev-1.13.0 y /v1/systemone.
            typesafe_base_url=_env("TYPESAFE_BASE_URL", "https://openrouter.ai/api").rstrip("/"),
            typesafe_model=_env("TYPESAFE_MODEL", "typesafe/jev-1.13"),
            typesafe_endpoint_path=_env("TYPESAFE_ENDPOINT_PATH", "/alpha/decisions"),
            semantic_timeout_seconds=_env_int("SEMANTIC_TIMEOUT_SECONDS", 15),
            semantic_max_attempts=_env_int("SEMANTIC_MAX_ATTEMPTS", 2),
            semantic_prompt_version=_env("SEMANTIC_PROMPT_VERSION", "jev-evidence-v1"),
            semantic_confidence_threshold=_env_optional_float(
                "SEMANTIC_CONFIDENCE_THRESHOLD"
            ),
        )
