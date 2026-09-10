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


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cors_origins: tuple[str, ...]
    max_upload_bytes: int
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str
    llm_max_retries: int
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
        llm_model = _env("LLM_MODEL") or _env("DEEPSEEK_MODEL") or "deepseek-chat"
        embedding_model = _env(
            "EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        query_prefix = _env("EMBEDDING_QUERY_PREFIX")
        passage_prefix = _env("EMBEDDING_PASSAGE_PREFIX")
        if not query_prefix and "e5" in embedding_model.lower():
            query_prefix = "query: "
            passage_prefix = "passage: "
        return cls(
            data_dir=data_dir,
            cors_origins=origins,
            max_upload_bytes=_env_int("MAX_UPLOAD_BYTES", 20 * 1024 * 1024),
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_max_retries=_env_int("LLM_MAX_RETRIES", 3),
            embedding_model=embedding_model,
            embedding_query_prefix=query_prefix,
            embedding_passage_prefix=passage_prefix,
            reranker_enabled=_env_bool("RERANKER_ENABLED", False),
            reranker_model=_env(
                "RERANKER_MODEL",
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
            ),
            rrf_lexical_weight=_env_float("RRF_LEXICAL_WEIGHT", 0.45),
            rrf_semantic_weight=_env_float("RRF_SEMANTIC_WEIGHT", 0.55),
            retrieval_top_k=_env_int("RETRIEVAL_TOP_K", 24),
            chunk_size=_env_int("CHUNK_SIZE", 1200),
            chunk_overlap=_env_int("CHUNK_OVERLAP", 180),
        )
