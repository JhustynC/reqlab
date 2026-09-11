from __future__ import annotations

from pathlib import Path
import hashlib
import re
from typing import Protocol

from .models import Fragment
from .retrieval import TfidfRetrievalAgent
from .settings import Settings


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbeddingProvider:
    """Embeddings multilingües locales; el modelo se carga bajo demanda."""

    def __init__(
        self,
        model_name: str,
        query_prefix: str = "",
        passage_prefix: str = "",
    ):
        self.model_name = model_name
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
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
        prefixed = [f"{self.passage_prefix}{text}" if self.passage_prefix else text for text in texts]
        vectors = self._load().encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        query = f"{self.query_prefix}{text}" if self.query_prefix else text
        vectors = self._load().encode([query], normalize_embeddings=True, show_progress_bar=False)
        return vectors[0].tolist()


class CrossEncoderReranker:
    """Reordena candidatos recuperados mediante un cross-encoder opcional."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as error:
                raise RuntimeError("La dependencia sentence-transformers no está instalada.") from error
            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self,
        query: str,
        candidates: list[tuple[Fragment, float]],
        top_k: int,
    ) -> list[tuple[Fragment, float]]:
        if not candidates:
            return []
        pairs = [(query, fragment.text) for fragment, _ in candidates]
        scores = self._load().predict(pairs)
        ranked = sorted(
            ((fragment, float(score)) for (fragment, _), score in zip(candidates, scores, strict=True)),
            key=lambda item: item[1],
            reverse=True,
        )
        return ranked[:top_k]


class ChromaProjectVectorStore:
    """Índice vectorial persistente de fragmentos separado por proyecto."""

    def __init__(
        self,
        persistence_path: str | Path,
        embedding_provider: EmbeddingProvider | None = None,
        collection_name: str = "requirements_fragments_v1",
    ):
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as error:
            raise RuntimeError("La dependencia chromadb no está instalada.") from error
        self.embedding_provider = embedding_provider or SentenceTransformerEmbeddingProvider(
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        path = Path(persistence_path)
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @classmethod
    def from_settings(cls, persistence_path: str | Path, settings: Settings) -> "ChromaProjectVectorStore":
        provider = SentenceTransformerEmbeddingProvider(
            settings.embedding_model,
            query_prefix=settings.embedding_query_prefix,
            passage_prefix=settings.embedding_passage_prefix,
        )
        # Cada modelo usa su propio espacio vectorial. Esto evita mezclar dimensiones
        # incompatibles cuando se cambia el modelo de embeddings entre experimentos.
        slug = re.sub(r"[^a-z0-9]+", "-", settings.embedding_model.lower()).strip("-")[:34]
        digest = hashlib.sha256(
            f"{settings.embedding_model}|{settings.embedding_query_prefix}|{settings.embedding_passage_prefix}".encode()
        ).hexdigest()[:10]
        return cls(persistence_path, provider, f"req-{slug}-{digest}")

    @staticmethod
    def _vector_id(project_id: str, fragment_id: str) -> str:
        return f"{project_id}:{fragment_id}"

    def index(self, project_id: str, fragments: list[Fragment], *, full_rebuild: bool = True) -> None:
        if full_rebuild:
            self.delete_project(project_id)
        self.upsert_fragments(project_id, fragments)

    def upsert_fragments(self, project_id: str, fragments: list[Fragment]) -> None:
        if not fragments:
            return
        batch_size = 64
        for start in range(0, len(fragments), batch_size):
            batch = fragments[start : start + batch_size]
            documents = [fragment.text for fragment in batch]
            self.collection.upsert(
                ids=[self._vector_id(project_id, fragment.fragment_id) for fragment in batch],
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

    def delete_fragments(self, project_id: str, fragment_ids: list[str]) -> None:
        if not fragment_ids:
            return
        try:
            self.collection.delete(ids=[self._vector_id(project_id, fragment_id) for fragment_id in fragment_ids])
        except Exception as error:
            if "empty" not in str(error).lower() and "nothing" not in str(error).lower():
                raise

    def delete_project(self, project_id: str) -> None:
        try:
            self.collection.delete(where={"project_id": project_id})
        except Exception as error:
            if "empty" not in str(error).lower() and "nothing" not in str(error).lower():
                raise

    def has_project(self, project_id: str) -> bool:
        result = self.collection.get(where={"project_id": project_id}, limit=1, include=[])
        return bool(result.get("ids"))

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
        reranker: CrossEncoderReranker | None = None,
        candidate_multiplier: int = 2,
    ):
        self.project_id = project_id
        self.fragments = fragments
        self.lexical = TfidfRetrievalAgent(fragments)
        self.vector_store = vector_store
        self.lexical_weight = lexical_weight
        self.semantic_weight = semantic_weight
        self.reranker = reranker
        self.candidate_multiplier = candidate_multiplier

    def retrieve(self, query: str, top_k: int = 12) -> list[tuple[Fragment, float]]:
        candidate_k = max(top_k * self.candidate_multiplier, 16)
        lexical = self.lexical.retrieve(query, top_k=candidate_k)
        semantic = self.vector_store.retrieve(self.project_id, query, top_k=candidate_k)
        fragments: dict[str, Fragment] = {}
        scores: dict[str, float] = {}
        for weight, ranking in ((self.lexical_weight, lexical), (self.semantic_weight, semantic)):
            for rank, (fragment, _) in enumerate(ranking, start=1):
                fragments[fragment.fragment_id] = fragment
                scores[fragment.fragment_id] = scores.get(fragment.fragment_id, 0.0) + weight / (60 + rank)
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:candidate_k]
        fused = [(fragments[fragment_id], score) for fragment_id, score in ordered]
        if self.reranker and fused:
            return self.reranker.rerank(query, fused, top_k)
        return fused[:top_k]
