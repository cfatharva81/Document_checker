"""Ingestion entry points for the extracted-document RAG layer."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from app.engine import all_rules, evaluate_all
from app.extractor import Doc
from app.rules.base import RuleConfig

from .adapter import load_extracted_document, load_extracted_documents
from .chunker import Chunk, chunk_document
from .generator import GeminiGenerator
from .prompts import RULE_QUESTIONS
from .retriever import ChunkRetriever, RuleAnswer


def ingest_extracted_file(path: str | Path,
						  target_tokens: int = 400,
						  max_tokens: int = 500,
						  overlap_paragraphs: int = 1) -> list[Chunk]:
	"""Load one extracted JSON file and return searchable chunks."""
	document = load_extracted_document(path)
	return chunk_document(
		document,
		target_tokens=target_tokens,
		max_tokens=max_tokens,
		overlap_paragraphs=overlap_paragraphs,
	)


def ingest_extracted_directory(directory: str | Path,
							   target_tokens: int = 400,
							   max_tokens: int = 500,
							   overlap_paragraphs: int = 1) -> list[Chunk]:
	"""Load every extracted JSON file in a directory and chunk each one."""
	chunks: list[Chunk] = []
	for document in load_extracted_documents(directory):
		chunks.extend(chunk_document(
			document,
			target_tokens=target_tokens,
			max_tokens=max_tokens,
			overlap_paragraphs=overlap_paragraphs,
		))
	return chunks


def evaluate_with_rule_engine(doc: Doc,
						  config: RuleConfig) -> list[RuleAnswer]:
	"""Run the existing deterministic engine using the RAG answer contract."""
	findings = evaluate_all(doc, config)
	return [RuleAnswer(
		rule_id=finding.rule_id,
		rule_name=finding.rule_name,
		# The public RAG contract is binary. An unevaluable rule is false and
		# retains the engine's message as evidence explaining why.
		passed=finding.passed is True,
		evidence=_finding_evidence(finding.message, finding.evidence),
		locations=list(finding.locations),
		method="rule_engine",
		confidence=finding.confidence,
	) for finding in findings]


def evaluate_with_gemini(retriever: ChunkRetriever,
						 generator: GeminiGenerator,
						 source: str | None = None,
						 top_k: int = 5) -> list[RuleAnswer]:
	"""Retrieve evidence and ask Gemini for all 13 binary rule decisions."""
	if top_k <= 0:
		raise ValueError("top_k must be positive")
	rule_names = {rule.id: rule.name for rule in all_rules()}
	answers: list[RuleAnswer] = []
	for rule_id in RULE_QUESTIONS:
		results = retriever.retrieve_for_rule(rule_id, top_k=top_k,
										 source=source)
		decision = generator.evaluate(rule_id, retriever.context(results))
		answers.append(RuleAnswer(
			rule_id=rule_id,
			rule_name=rule_names.get(rule_id, f"Rule {rule_id}"),
			passed=decision.passed,
			evidence=decision.evidence,
			locations=decision.locations,
			method="gemini",
			confidence="heuristic",
		))
	return answers


def evaluate(mode: Literal["rule_engine", "gemini"], *,
			 doc: Doc | None = None,
			 config: RuleConfig | None = None,
			 retriever: ChunkRetriever | None = None,
			 generator: GeminiGenerator | None = None,
			 source: str | None = None,
			 top_k: int = 5) -> list[RuleAnswer]:
	"""Evaluate rules through the selected deterministic or Gemini path."""
	if mode == "rule_engine":
		if doc is None:
			raise ValueError("doc is required for rule_engine mode")
		return evaluate_with_rule_engine(doc, config or RuleConfig())
	if mode == "gemini":
		if retriever is None or generator is None:
			raise ValueError("retriever and generator are required for gemini mode")
		return evaluate_with_gemini(retriever, generator, source, top_k)
	raise ValueError("mode must be 'rule_engine' or 'gemini'")


def _finding_evidence(message: str, evidence: list[str]) -> str:
	parts = [message.strip()] + [item.strip() for item in evidence if item.strip()]
	return " ".join(part for part in parts if part)
