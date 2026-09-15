import json
from pathlib import Path

from app.rag.adapter import load_extracted_documents
from app.rag.pipeline import ingest_extracted_directory, ingest_extracted_file


def test_load_extracted_documents_uses_sorted_json_files(tmp_path: Path):
	(tmp_path / "b.extracted.json").write_text(
		'{"filename": "b.docx", "blocks": []}', encoding="utf-8")
	(tmp_path / "a.extracted.json").write_text(
		'{"filename": "a.docx", "blocks": []}', encoding="utf-8")
	(tmp_path / "ignore.json").write_text("{}", encoding="utf-8")

	documents = load_extracted_documents(tmp_path)

	assert [document.filename for document in documents] == ["a.docx", "b.docx"]


def test_ingestion_pipeline_returns_chunks_for_file_and_directory(tmp_path: Path):

	content = {
		"filename": "a.docx",
		"blocks": [{
			"block_index": 0,
			"kind": "paragraph",
			"text": "Purpose",
			"props": {"heading_level": 1},
		}],
	}
	path = tmp_path / "a.extracted.json"
	path.write_text(json.dumps(content), encoding="utf-8")

	assert len(ingest_extracted_file(path)) == 1
	assert len(ingest_extracted_directory(tmp_path)) == 1
