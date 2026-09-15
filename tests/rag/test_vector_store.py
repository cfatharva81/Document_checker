from app.rag.chunker import Chunk
from app.rag.vector_store import InMemoryVectorStore


def _chunk(chunk_id, source="a.docx", section=None):
	return Chunk(
		id=chunk_id,
		text=chunk_id,
		metadata={"source": source, "section_path": section or []},
	)


def test_vector_store_ranks_and_filters_chunks():
	store = InMemoryVectorStore(dimension=3)
	store.add(
		[_chunk("best"), _chunk("other"), _chunk("different", "b.docx")],
		[[1, 0, 0], [0, 1, 0], [1, 0, 0]],
	)

	results = store.search([1, 0, 0], top_k=2, source="a.docx")

	assert [result.chunk.id for result in results] == ["best", "other"]
	assert results[0].score == 1.0


def test_vector_store_persists_chunks_and_vectors(tmp_path):
	path = tmp_path / "vectors.json"
	store = InMemoryVectorStore(dimension=3)
	store.add([_chunk("one")], [[1, 2, 3]])
	store.save(path)

	loaded = InMemoryVectorStore.load(path)
	results = loaded.search([1, 2, 3])

	assert len(loaded) == 1
	assert results[0].chunk.text == "one"
	assert results[0].score > 0.99


def test_vector_store_rejects_wrong_dimensions():
	store = InMemoryVectorStore(dimension=3)

	try:
		store.add([_chunk("bad")], [[1, 0]])
	except ValueError as exc:
		assert "dimensions" in str(exc)
	else:
		assert False, "wrong vector dimensions should be rejected"