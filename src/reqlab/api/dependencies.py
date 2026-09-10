from __future__ import annotations

from functools import lru_cache

from ..generation import load_local_env
from ..llm import OpenAICompatibleClient
from ..services import ProjectApplicationService
from ..settings import Settings
from ..storage import SQLiteRepository
from ..vector_store import ChromaProjectVectorStore, CrossEncoderReranker


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_local_env()
    settings = Settings.from_environment()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings


@lru_cache(maxsize=1)
def get_repository() -> SQLiteRepository:
    return SQLiteRepository(get_settings().data_dir / "requirements.db")


@lru_cache(maxsize=1)
def get_vector_store() -> ChromaProjectVectorStore:
    settings = get_settings()
    return ChromaProjectVectorStore.from_settings(settings.data_dir / "chroma", settings)


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker | None:
    settings = get_settings()
    if not settings.reranker_enabled:
        return None
    return CrossEncoderReranker(settings.reranker_model)


@lru_cache(maxsize=1)
def get_client() -> OpenAICompatibleClient:
    settings = get_settings()
    return OpenAICompatibleClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        max_retries=settings.llm_max_retries,
    )


@lru_cache(maxsize=1)
def get_service() -> ProjectApplicationService:
    return ProjectApplicationService(
        get_repository(),
        get_vector_store(),
        get_settings().data_dir,
        get_client(),
        settings=get_settings(),
    )
