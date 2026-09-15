"""MiniLM embeddings for extracted-document chunks."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .chunker import Chunk

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


class MiniLMEmbedder:
    """Encode document chunks and queries with all-MiniLM-L6-v2.

    The model is loaded lazily when no model is injected. Tests and callers
    that manage model lifecycle themselves can pass a SentenceTransformer-
    compatible object through ``model``.
    """

    dimension = EMBEDDING_DIMENSION
    model_name = MODEL_NAME

    def __init__(
        self,
        model: Any = None,
        model_name: str = MODEL_NAME,
        device: str | None = None,
        batch_size: int = 32,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size

        if model is not None:
            self._model = model
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Embeddings require sentence-transformers. "
                "Install dependencies with: pip install -r requirements.txt"
            ) from exc

        kwargs = {"device": device} if device else {}
        self._model = SentenceTransformer(model_name, **kwargs)

    def encode_documents(
        self,
        chunks: Sequence[Chunk] | Sequence[str],
    ) -> list[list[float]]:
        """Encode chunk text."""
        texts = [
            chunk.text if isinstance(chunk, Chunk) else chunk
            for chunk in chunks
        ]
        return self._encode(texts)

    def encode_query(self, query: str) -> list"""Encode a user query."""
        if not query or not query.strip():
            raise ValueError("query must contain non-whitespace text")

        vectors = self._encode([query.strip()])
        return vectors[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        if hasattr(vectors, "tolist"):
            vectors = vectors.tolist()

        if vectors and isinstance(vectors[0], (int, float)):
            vectors = [vectors]

        return [
            [float(value) for value in vector]
            for vector in vectors
        ]