"""Retrieval and evidence formatting for rule evaluation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .chunker import Chunk
from .prompts import rule_question
from .vector_store import InMemoryVectorStore, SearchResult


@dataclass(frozen=True)
class RuleAnswer:
	rule_id: int
	rule_name: str
	passed: bool
	evidence: str
	locations: list[str] = field(default_factory=list)
	method: str = "rule_engine"
	confidence: str = "certain"


class ChunkRetriever:
	"""Retrieve chunks for rule questions using the configured embedder."""

	def __init__(self, store: InMemoryVectorStore, embedder: Any) -> None:
		self.store = store
		self.embedder = embedder

	def retrieve(self, question: str, top_k: int = 5,
				source: str | None = None) -> list[SearchResult]:
		return self.store.search_text(
			question, self.embedder, top_k=top_k, source=source)

	def retrieve_for_rule(self, rule_id: int, top_k: int = 5,
						 source: str | None = None) -> list[SearchResult]:
		return self.retrieve(rule_question(rule_id), top_k=top_k,
						 source=source)

	def context(self, results: Sequence[SearchResult]) -> str:
		"""Format retrieved chunks with human-readable traceability."""
		if not results:
			return "No relevant document evidence was retrieved."
		parts: list[str] = []
		for index, result in enumerate(results, start=1):
			chunk = result.chunk
			metadata = chunk.metadata
			source = metadata.get("source", "unknown source")
			locations = ", ".join(metadata.get("locations", [])) or "unknown location"
			section = " > ".join(metadata.get("section_path", [])) or "body"
			parts.append(
				f"Evidence {index} (similarity {result.score:.3f})\n"
				f"Source: {source}\nSection: {section}\n"
				f"Location: {locations}\nText: {chunk.text}"
			)
		return "\n\n".join(parts)
