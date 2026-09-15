"""A small local vector store for chunk embeddings."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .chunker import Chunk


@dataclass(frozen=True)
class SearchResult:
	chunk: Chunk
	score: float


@dataclass(frozen=True)
class _StoredItem:
	chunk: Chunk
	vector: tuple[float, ...]


class InMemoryVectorStore:
	"""Store normalized or unnormalized vectors and rank them by cosine score.

	The store is intentionally provider-neutral. Embeddings are created by
	``BGEEmbedder`` and only supplied here as numeric vectors.
	"""

	def __init__(self, dimension: int = 768) -> None:
		if dimension <= 0:
			raise ValueError("dimension must be positive")
		self.dimension = dimension
		self._items: dict[str, _StoredItem] = {}

	def add(self, chunks: Sequence[Chunk],
			vectors: Sequence[Sequence[float]]) -> None:
		"""Insert or replace chunks and their embeddings by chunk ID."""
		if len(chunks) != len(vectors):
			raise ValueError("chunks and vectors must have the same length")
		for chunk, vector in zip(chunks, vectors):
			validated = self._validate_vector(vector)
			self._items[chunk.id] = _StoredItem(chunk, validated)

	def search(self, query_vector: Sequence[float], top_k: int = 5,
			   source: str | None = None,
			   section_path: Sequence[str] | None = None
			   ) -> list[SearchResult]:
		"""Return the highest-scoring chunks matching optional metadata."""
		if top_k <= 0:
			raise ValueError("top_k must be positive")
		query = self._validate_vector(query_vector)
		query_norm = _norm(query)
		results: list[SearchResult] = []
		for item in self._items.values():
			if source is not None and item.chunk.metadata.get("source") != source:
				continue
			if (section_path is not None and
				item.chunk.metadata.get("section_path") != list(section_path)):
				continue
			score = _dot(query, item.vector) / (query_norm * _norm(item.vector))
			results.append(SearchResult(item.chunk, score))
		results.sort(key=lambda result: result.score, reverse=True)
		return results[:top_k]

	def search_text(self, query: str, embedder: Any, top_k: int = 5,
					 source: str | None = None,
					 section_path: Sequence[str] | None = None
					 ) -> list[SearchResult]:
		"""Embed a query with the supplied embedder and search the store."""
		return self.search(
			embedder.encode_query(query),
			top_k=top_k,
			source=source,
			section_path=section_path,
		)

	def save(self, path: str | Path) -> None:
		"""Persist vectors and chunk metadata as a portable JSON file."""
		payload = {
			"dimension": self.dimension,
			"items": [
				{
					"chunk": asdict(item.chunk),
					"vector": list(item.vector),
				}
				for item in self._items.values()
			],
		}
		with Path(path).open("w", encoding="utf-8") as handle:
			json.dump(payload, handle, ensure_ascii=False)

	@classmethod
	def load(cls, path: str | Path) -> "InMemoryVectorStore":
		"""Load a store previously written by ``save``."""
		with Path(path).open("r", encoding="utf-8") as handle:
			payload = json.load(handle)
		store = cls(dimension=payload["dimension"])
		for item in payload.get("items", []):
			chunk_data = item["chunk"]
			chunk = Chunk(
				id=chunk_data["id"],
				text=chunk_data["text"],
				metadata=chunk_data.get("metadata") or {},
			)
			store.add([chunk], [item["vector"]])
		return store

	def __len__(self) -> int:
		return len(self._items)

	def _validate_vector(self, vector: Sequence[float]) -> tuple[float, ...]:
		if len(vector) != self.dimension:
			raise ValueError(
				f"expected vectors with {self.dimension} dimensions, "
				f"got {len(vector)}"
			)
		values = tuple(float(value) for value in vector)
		if not all(math.isfinite(value) for value in values):
			raise ValueError("vectors must contain only finite values")
		if _norm(values) == 0:
			raise ValueError("vectors must not be zero vectors")
		return values


def _dot(left: Iterable[float], right: Iterable[float]) -> float:
	return sum(a * b for a, b in zip(left, right))


def _norm(vector: Iterable[float]) -> float:
	return math.sqrt(_dot(vector, vector))
