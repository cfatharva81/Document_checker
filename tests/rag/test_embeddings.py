import pytest

from app.rag.chunker import Chunk
from app.rag.embeddings import (
	BGEEmbedder,
	EMBEDDING_DIMENSION,
	QUERY_PREFIX,
)


class FakeEmbeddingModel:
	def __init__(self):
		self.calls = []

	def encode(self, texts, **kwargs):
		self.calls.append((texts, kwargs))
		return [[0.5] * EMBEDDING_DIMENSION for _ in texts]


def test_bge_encodes_chunks_and_queries_with_expected_options():
	model = FakeEmbeddingModel()
	embedder = BGEEmbedder(model=model, batch_size=7)

	document_vectors = embedder.encode_documents([
		Chunk(id="1", text="Revision history", metadata={}),
	])
	query_vector = embedder.encode_query("Where is the revision history?")

	assert len(document_vectors) == 1
	assert len(document_vectors[0]) == 768
	assert len(query_vector) == 768
	assert model.calls[0][0] == ["Revision history"]
	assert model.calls[1][0] == [
		QUERY_PREFIX + "Where is the revision history?"
	]
	for _, options in model.calls:
		assert options["normalize_embeddings"] is True
		assert options["convert_to_numpy"] is True
		assert options["batch_size"] == 7


def test_bge_handles_empty_documents_and_rejects_blank_query():
	embedder = BGEEmbedder(model=FakeEmbeddingModel())

	assert embedder.encode_documents([]) == []
	with pytest.raises(ValueError, match="query"):
		embedder.encode_query("  ")