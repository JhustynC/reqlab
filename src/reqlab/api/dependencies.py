from __future__ import annotations

from functools import lru_cache

from ..generation import load_local_env
from ..llm import DeepSeekClient
from ..services import ProjectApplicationService
from ..settings import Settings
from ..storage import SQLiteRepository
from ..vector_store import ChromaProjectVectorStore


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
    return ChromaProjectVectorStore(get_settings().data_dir / "chroma")


@lru_cache(maxsize=1)
def get_client() -> DeepSeekClient:
    return DeepSeekClient()


@lru_cache(maxsize=1)
def get_service() -> ProjectApplicationService:
    return ProjectApplicationService(
        get_repository(),
        get_vector_store(),
        get_settings().data_dir,
        get_client(),
    )

