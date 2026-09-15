"""Load extracted ``Doc`` JSON into a small RAG-facing representation."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ExtractedRecord:
	"""One searchable unit in the document's original reading order."""

	text: str
	block_index: int
	location: str
	kind: str = "paragraph"
	heading_level: int | None = None
	table_index: int | None = None
	metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedDocument:
	filename: str
	records: tuple[ExtractedRecord, ...]
	core: dict[str, Any] = field(default_factory=dict)


def load_extracted_document(path: str | Path) -> ExtractedDocument:
	"""Load one file written by ``app.pipeline.save_extraction``."""
	source = Path(path)
	with source.open("r", encoding="utf-8") as handle:
		payload = json.load(handle)
	return extracted_document_from_dict(payload)


def load_extracted_documents(directory: str | Path) -> list[ExtractedDocument]:
	"""Load all extracted JSON files in deterministic filename order."""
	root = Path(directory)
	return [load_extracted_document(path)
			for path in sorted(root.glob("*.extracted.json"))]


def extracted_document_from_dict(payload: dict[str, Any]) -> ExtractedDocument:
	"""Convert the serialized extractor model into ordered RAG records."""
	tables = {
		table.get("table_index"): table
		for table in payload.get("tables", [])
	}
	records: list[ExtractedRecord] = []
	for block in sorted(payload.get("blocks", []),
						key=lambda item: item.get("block_index", 0)):
		kind = block.get("kind", "paragraph")
		if kind == "table":
			table_index = block.get("table_index")
			table = tables.get(table_index)
			text = _table_text(table)
			if text:
				records.append(ExtractedRecord(
					text=text,
					block_index=block.get("block_index", 0),
					location=block.get("location", f"Table {table_index}"),
					kind="table",
					table_index=table_index,
					metadata={"table_index": table_index},
				))
			continue

		text = _clean_text(block.get("text"))
		if not text:
			continue
		props = block.get("props") or {}
		level = props.get("heading_level")
		if level is None:
			level = props.get("inferred_heading_level")
		records.append(ExtractedRecord(
			text=text,
			block_index=block.get("block_index", 0),
			location=block.get("location", ""),
			heading_level=level,
			metadata={
				"in_table": bool(block.get("in_table")),
				"from_textbox": bool(block.get("from_textbox")),
				"table_pos": block.get("table_pos"),
			},
		))
	return ExtractedDocument(
		filename=payload.get("filename", "document.docx"),
		records=tuple(records),
		core=payload.get("core") or {},
	)


def _table_text(table: dict[str, Any] | None) -> str:
	if not table:
		return ""
	rows: list[str] = []
	for row in table.get("rows", []):
		cells = []
		for cell in row.get("cells", []):
			cell_text = "\n".join(
				text for text in (_clean_text(block.get("text"))
								  for block in cell.get("blocks", []))
				if text
			)
			cells.append(cell_text)
		if any(cells):
			rows.append(" | ".join(cells))
	return "\n".join(rows)


def _clean_text(value: Any) -> str:
	if not isinstance(value, str):
		return ""
	return " ".join(value.split())
