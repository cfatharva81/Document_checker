from app.rag.generator import GeminiDecision, GeminiGenerator
from app.rag.pipeline import evaluate
from app.rag.retriever import ChunkRetriever
from app.rag.vector_store import InMemoryVectorStore
from app.rag.chunker import Chunk


class FakeEmbedder:
	def encode_query(self, query):
		return [1, 0, 0]


class FakeGenerator:
	def evaluate(self, rule_id, context):
		assert context == "retrieved evidence"
		return GeminiDecision(
			passed=rule_id % 2 == 0,
			evidence=f"Evidence for rule {rule_id}.",
			locations=[f"Paragraph {rule_id}"],
		)


class FakeRetriever:
	def retrieve_for_rule(self, rule_id, top_k, source):
		assert top_k == 2
		return []

	def context(self, results):
		return "retrieved evidence"


def test_retriever_formats_traceable_context():
	store = InMemoryVectorStore(dimension=3)
	store.add([Chunk(
		id="chunk-1",
		text="Revision 1.0",
		metadata={"source": "sop.docx", "section_path": ["Revision History"],
				  "locations": ["Table 1"]},
	)], [[1, 0, 0]])

	retriever = ChunkRetriever(store, FakeEmbedder())
	context = retriever.context(retriever.retrieve("version", top_k=1))

	assert "Source: sop.docx" in context
	assert "Section: Revision History" in context
	assert "Location: Table 1" in context
	assert "Revision 1.0" in context


def test_gemini_parser_requires_boolean_and_evidence():
	decision = GeminiGenerator._parse(
		'{"passed": false, "evidence": "Missing footer.", '
		'"locations": ["Footer, section 1"]}'
	)

	assert decision.passed is False
	assert decision.evidence == "Missing footer."


def test_gemini_mode_returns_all_thirteen_binary_answers():
	answers = evaluate(
		"gemini",
		retriever=FakeRetriever(),
		generator=FakeGenerator(),
		top_k=2,
	)

	assert len(answers) == 13
	assert {answer.passed for answer in answers} == {True, False}
	assert all(answer.method == "gemini" for answer in answers)