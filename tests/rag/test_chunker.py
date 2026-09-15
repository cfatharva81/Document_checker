from app.rag.adapter import extracted_document_from_dict
from app.rag.chunker import chunk_document


def test_chunker_creates_heading_path_and_does_not_cross_headings():
	document = extracted_document_from_dict({
		"filename": "sample.docx",
		"blocks": [
			{"block_index": 0, "kind": "paragraph", "text": "Purpose",
			 "props": {"heading_level": 1}},
			{"block_index": 1, "kind": "paragraph", "text": "First body",
			 "props": {}},
			{"block_index": 2, "kind": "paragraph", "text": "Scope",
			 "props": {"heading_level": 1}},
			{"block_index": 3, "kind": "paragraph", "text": "Second body",
			 "props": {}},
		],
	})

	chunks = chunk_document(document, target_tokens=10, max_tokens=20,
							overlap_paragraphs=1)

	assert len(chunks) == 2
	assert chunks[0].metadata["section_path"] == ["Purpose"]
	assert chunks[1].metadata["section_path"] == ["Scope"]
	assert "Second body" in chunks[1].text
	assert "First body" not in chunks[1].text


def test_chunker_keeps_table_metadata():
	document = extracted_document_from_dict({
		"filename": "sample.docx",
		"blocks": [{"block_index": 0, "kind": "table", "table_index": 4}],
		"tables": [{"table_index": 4, "rows": [{"cells": [
			{"blocks": [{"text": "Version"}]},
			{"blocks": [{"text": "Date"}]},
		]}]}],
	})

	chunks = chunk_document(document)

	assert chunks[0].metadata["content_type"] == "table"
	assert chunks[0].metadata["table_indices"] == [4]
