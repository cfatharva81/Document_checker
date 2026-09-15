"""Structure-aware chunking for extracted SOP documents."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapter import ExtractedDocument, ExtractedRecord


@dataclass(frozen=True)
class Chunk:
	id: str
	text: str
	metadata: dict[str, Any]


def chunk_document(document: ExtractedDocument,
				   target_tokens: int = 400,
				   max_tokens: int = 500,
				   overlap_paragraphs: int = 1) -> list[Chunk]:
	"""Chunk a document at headings and paragraph boundaries.

	Token counts are estimated without requiring a tokenizer dependency.
	Headings define boundaries, tables remain atomic unless they exceed the
	maximum, and one trailing body paragraph is carried into the next chunk.
	"""
	if target_tokens <= 0 or max_tokens < target_tokens:
		raise ValueError("max_tokens must be at least target_tokens > 0")
	if overlap_paragraphs < 0:
		raise ValueError("overlap_paragraphs cannot be negative")

	chunks: list[Chunk] = []
	pending: list[ExtractedRecord] = []
	heading_path: list[str] = []
	sequence = 0

	def flush(with_overlap: bool = True) -> None:
		nonlocal pending, sequence
		if not pending:
			return
		chunks.append(_make_chunk(document, pending, heading_path, sequence))
		sequence += 1
		if with_overlap:
			carry = [record for record in pending
					 if record.kind == "paragraph" and
					 record.heading_level is None]
			pending = carry[-overlap_paragraphs:] if overlap_paragraphs else []
		else:
			pending = []

	for record in document.records:
		if record.heading_level is not None:
			flush(with_overlap=False)
			level = max(1, record.heading_level)
			heading_path[:] = heading_path[:level - 1]
			heading_path.append(record.text)
			pending.append(record)
			continue

		pieces = _split_record(record, max_tokens)
		if len(pieces) > 1:
			flush(with_overlap=False)
			for piece in pieces:
				chunks.append(_make_chunk(document, [piece], heading_path,
										  sequence))
				sequence += 1
			continue

		record_tokens = _estimate_tokens(record.text)
		pending_tokens = _estimate_tokens(" ".join(r.text for r in pending))
		if pending and pending_tokens >= target_tokens:
			flush()
		if pending and pending_tokens + record_tokens > max_tokens:
			flush()
		pending.append(record)

	flush(with_overlap=False)
	return chunks


def _make_chunk(document: ExtractedDocument,
				records: list[ExtractedRecord],
				heading_path: list[str],
				sequence: int) -> Chunk:
	text = "\n\n".join(record.text for record in records)
	block_indices = [record.block_index for record in records]
	locations = [record.location for record in records if record.location]
	kinds = {record.kind for record in records}
	metadata: dict[str, Any] = {
		"source": document.filename,
		"section_path": list(heading_path),
		"block_start": min(block_indices),
		"block_end": max(block_indices),
		"locations": locations,
		"content_type": "table" if kinds == {"table"} else "mixed"
		if "table" in kinds else "paragraphs",
	}
	table_indices = [record.table_index for record in records
					 if record.table_index is not None]
	if table_indices:
		metadata["table_indices"] = table_indices
	return Chunk(
		id=f"{document.filename}:{sequence}",
		text=text,
		metadata=metadata,
	)


def _split_record(record: ExtractedRecord,
				  max_tokens: int) -> list[ExtractedRecord]:
	if _estimate_tokens(record.text) <= max_tokens:
		return [record]
	if record.kind == "table":
		lines = record.text.splitlines()
		header = lines[:1]
		pieces: list[ExtractedRecord] = []
		current = list(header)
		for line in lines[1:]:
			candidate = "\n".join(current + [line])
			if len(current) > 1 and _estimate_tokens(candidate) > max_tokens:
				pieces.append(_record_with_text(record, "\n".join(current)))
				current = list(header)
			current.append(line)
		if current and (len(current) > 1 or not pieces):
			pieces.append(_record_with_text(record, "\n".join(current)))
		return pieces

	words = record.text.split()
	pieces = []
	current: list[str] = []
	for word in words:
		if current and _estimate_tokens(" ".join(current + [word])) > max_tokens:
			pieces.append(_record_with_text(record, " ".join(current)))
			current = []
		current.append(word)
	if current:
		pieces.append(_record_with_text(record, " ".join(current)))
	return pieces


def _record_with_text(record: ExtractedRecord, text: str) -> ExtractedRecord:
	return ExtractedRecord(
		text=text,
		block_index=record.block_index,
		location=record.location,
		kind=record.kind,
		heading_level=record.heading_level,
		table_index=record.table_index,
		metadata=record.metadata,
	)


def _estimate_tokens(text: str) -> int:
	"""Conservative English token estimate for dependency-free chunking."""
	words = len(text.split())
	return max(1, (words * 4 + 2) // 3) if words else 0
