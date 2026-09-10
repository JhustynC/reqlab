from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from .models import Fragment
from .retrieval import TfidfRetrievalAgent


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbeddingProvider:
    """Embeddings multilingües locales; el modelo se carga bajo demanda."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise RuntimeError("La dependencia sentence-transformers no está instalada.") from error
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._load().encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class ChromaProjectVectorStore:
    """Índice vectorial persistente de fragmentos separado por proyecto."""

    def __init__(self, persistence_path: str | Path, embedding_provider: EmbeddingProvider | None = None):
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as error:
            raise RuntimeError("La dependencia chromadb no está instalada.") from error
        self.embedding_provider = embedding_provider or SentenceTransformerEmbeddingProvider()
        path = Path(persistence_path)
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(path),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="requirements_fragments",
            metadata={"hnsw:space": "cosine"},
        )

    def index(self, project_id: str, fragments: list[Fragment]) -> None:
        if not fragments:
            return
        self.delete_project(project_id)
        batch_size = 64
        for start in range(0, len(fragments), batch_size):
            batch = fragments[start : start + batch_size]
            documents = [fragment.text for fragment in batch]
            self.collection.upsert(
                ids=[f"{project_id}:{fragment.fragment_id}" for fragment in batch],
                documents=documents,
                embeddings=self.embedding_provider.embed_documents(documents),
                metadatas=[
                    {
                        "project_id": project_id,
                        "fragment_id": fragment.fragment_id,
                        "source_id": fragment.source_id,
                        "source_file": fragment.source_file,
                        "heading": fragment.heading,
                    }
                    for fragment in batch
                ],
            )

    def delete_project(self, project_id: str) -> None:
        try:
            self.collection.delete(where={"project_id": project_id})
        except Exception as error:
            # Chroma puede rechazar el delete si la colección aún está vacía.
            if "empty" not in str(error).lower() and "nothing" not in str(error).lower():
                raise

    def retrieve(self, project_id: str, query: str, top_k: int = 12) -> list[tuple[Fragment, float]]:
        result = self.collection.query(
            query_embeddings=[self.embedding_provider.embed_query(query)],
            n_results=max(1, top_k),
            where={"project_id": project_id},
            include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        recovered: list[tuple[Fragment, float]] = []
        for document, metadata, distance in zip(documents, metadatas, distances, strict=True):
            fragment = Fragment(
                fragment_id=str(metadata["fragment_id"]),
                source_id=str(metadata["source_id"]),
                source_file=str(metadata["source_file"]),
                heading=str(metadata["heading"]),
                text=str(document),
            )
            recovered.append((fragment, max(0.0, 1.0 - float(distance))))
        return recovered


class HybridRetrievalAgent:
    """Fusiona ranking léxico y semántico mediante Reciprocal Rank Fusion."""

    def __init__(
        self,
        project_id: str,
        fragments: list[Fragment],
        vector_store: ChromaProjectVectorStore,
        lexical_weight: float = 0.45,
        semantic_weight: float = 0.55,
    ):
        self.project_id = project_id
        self.fragments = fragments
        self.lexical = TfidfRetrievalAgent(fragments)
        self.vector_store = vector_store
        self.lexical_weight = lexical_weight
        self.semantic_weight = semantic_weight

    def retrieve(self, query: str, top_k: int = 12) -> list[tuple[Fragment, float]]:
        candidate_k = max(top_k * 2, 16)
        lexical = self.lexical.retrieve(query, top_k=candidate_k)
        semantic = self.vector_store.retrieve(self.project_id, query, top_k=candidate_k)
        fragments: dict[str, Fragment] = {}
        scores: dict[str, float] = {}
        for weight, ranking in ((self.lexical_weight, lexical), (self.semantic_weight, semantic)):
            for rank, (fragment, _) in enumerate(ranking, start=1):
                fragments[fragment.fragment_id] = fragment
                scores[fragment.fragment_id] = scores.get(fragment.fragment_id, 0.0) + weight / (60 + rank)
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        return [(fragments[fragment_id], score) for fragment_id, score in ordered]
