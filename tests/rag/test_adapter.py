from app.rag.adapter import extracted_document_from_dict


def test_adapter_keeps_flow_order_and_drops_empty_paragraphs():
	document = extracted_document_from_dict({
		"filename": "sample.docx",
		"blocks": [
			{"block_index": 2, "kind": "paragraph", "text": "Body",
			 "props": {}},
			{"block_index": 1, "kind": "paragraph", "text": " ",
			 "props": {}},
			{"block_index": 3, "kind": "table", "table_index": 0,
			 "location": "Table 1"},
		],
		"tables": [{"table_index": 0, "rows": [{"cells": [
			{"blocks": [{"text": "Name"}]},
			{"blocks": [{"text": "Value"}]},
		]}]}],
	})

	assert [record.kind for record in document.records] == ["paragraph", "table"]
	assert document.records[1].text == "Name | Value"


def test_adapter_prefers_explicit_heading_level():
	document = extracted_document_from_dict({
		"filename": "sample.docx",
		"blocks": [{
			"block_index": 0,
			"kind": "paragraph",
			"text": "Purpose",
			"props": {"heading_level": 1, "inferred_heading_level": 2},
		}],
	})

	assert document.records[0].heading_level == 1
