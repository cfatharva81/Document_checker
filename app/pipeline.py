"""The analysis pipeline: takes raw file bytes in, hands findings back out.

This is the one place that owns the whole path an upload takes - validate
it, extract it, run the rules, summarise the results. That keeps the API
route handlers thin, and means the whole thing can be run directly from a
test or a script, without needing FastAPI at all.

The LanguageTool adapter lives here too, since it's the one rule dependency
that needs a shared, process-wide resource. Rule 9 itself should never
import language_tool_python directly.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import threading
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from app.extractor import Doc, build_doc
from app.engine import evaluate_all, get_rule, run_rule
from app.rules.base import Finding, LanguageIssue, RuleConfig
from app.rules.rule_09_language import DISABLED_RULE_IDS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTPUT_DIR = os.path.join(ROOT, "output")
INPUT_DIR = os.path.join(ROOT, "input")

log = logging.getLogger(__name__)

MAX_MB = 20
MAX_BYTES = MAX_MB * 1024 * 1024
_ZIP_MAGIC = b"PK\x03\x04"

# disabled here for speed - rule 9 also filters these out itself, just in case
_DISABLED = sorted(DISABLED_RULE_IDS)


class UploadRejected(Exception):
    """A bad upload, with the HTTP status the API should report."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# --------------------------------------------------------------------------
# LanguageTool
# --------------------------------------------------------------------------
class LanguageToolChecker:
    """Wraps a language_tool_python instance so it matches the
    LanguageChecker protocol, and makes sure only one thread uses it
    at a time."""

    def __init__(self, tool, lock: threading.Lock):
        self._tool = tool
        self._lock = lock

    def check(self, text: str) -> list[LanguageIssue]:
        if not text.strip():
            return []
        with self._lock:
            matches = self._tool.check(text)
        issues = []
        for m in matches:
            issues.append(LanguageIssue(
                message=getattr(m, "message", ""),
                context=getattr(m, "context", "") or "",
                offset=getattr(m, "offset", 0),
                # snake_case (language_tool_python >= 2.6) with camelCase fallback
                length=getattr(m, "error_length",
                               getattr(m, "errorLength", 0)),
                rule_id=getattr(m, "rule_id", getattr(m, "ruleId", "")),
                matched_text=getattr(m, "matched_text",
                                     getattr(m, "matchedText", "")) or "",
                replacements=list(getattr(m, "replacements", []) or [])[:5],
            ))
        return issues


def create_language_tool():
    """Create the LanguageTool instance. The first time this runs, it
    downloads LanguageTool's jar file and starts a JVM, so it's slow.

    The import is done inside this function, not at the top of the file,
    so that just importing this module doesn't require language_tool_python
    to be installed - useful in tests that provide their own stub checker.
    """
    import language_tool_python

    tool = language_tool_python.LanguageTool("en-US")
    try:
        tool.disabled_rules.update(_DISABLED)
    except Exception:
        pass
    return tool


def build_checker(existing_tool=None,
                  lock: Optional[threading.Lock] = None) -> LanguageToolChecker:
    lock = lock or threading.Lock()
    tool = existing_tool or create_language_tool()
    return LanguageToolChecker(tool, lock)


# --------------------------------------------------------------------------
# Upload -> Doc
# --------------------------------------------------------------------------
def validate_upload(filename: Optional[str], stream) -> tuple[str, bytes]:
    """Check the file extension, size, and zip signature, before handing
    anything to python-docx."""
    name = filename or "document.docx"
    if not name.lower().endswith(".docx"):
        raise UploadRejected(
            415, "Only .docx files are accepted (got a different type).")
    data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise UploadRejected(
            413, f"File exceeds the {MAX_MB} MB upload limit.")
    if len(data) < 4 or data[:4] != _ZIP_MAGIC:
        raise UploadRejected(
            422, "File is not a valid .docx (OOXML zip) package.")
    return name, data


def extract(filename: Optional[str], stream) -> tuple[str, Doc, bytes]:
    """Validate an upload and turn it into the Doc model the rules use.

    The raw bytes are returned too, alongside the Doc. They're the exact
    input that produced it, the stream has already been read to the end by
    this point, and save_source() needs those bytes to keep a copy - this
    is the only place it can get them from.
    """
    name, data = validate_upload(filename, stream)
    try:
        return name, build_doc(io.BytesIO(data), name), data
    except Exception as exc:
        raise UploadRejected(422, f"Could not parse the document: {exc}")


# --------------------------------------------------------------------------
# Doc -> findings
# --------------------------------------------------------------------------
def analyze(doc: Doc, config: RuleConfig) -> list[Finding]:
    return evaluate_all(doc, config)


def analyze_one(rule_id: int, doc: Doc, config: RuleConfig) -> Finding:
    rule = get_rule(rule_id)
    if rule is None:
        raise UploadRejected(404, f"No rule with id {rule_id}.")
    return run_rule(rule, doc, config)


def doc_to_dict(doc: Doc) -> dict:
    """Turn the Doc model into plain dicts that can be dumped as JSON,
    for the /api/extract endpoint."""
    data = asdict(doc)
    core = data.get("core") or {}
    for key in ("created", "modified"):
        val = core.get(key)
        if isinstance(val, datetime):
            core[key] = val.isoformat()
    return data


# --------------------------------------------------------------------------
# Extraction output - the Doc model gets written to output/ so we can look
# back at exactly what the rules saw, after the fact
# --------------------------------------------------------------------------
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def output_stem(filename: Optional[str]) -> str:
    """Turn a client-supplied filename into a safe stem for saving to disk.

    Only the basename is kept, and anything that isn't a letter, digit,
    dot, underscore or dash gets replaced. This way a malicious filename
    can't be used to write a file outside OUTPUT_DIR.
    """
    base = os.path.basename(filename or "document.docx")
    base = re.sub(r"\.docx$", "", base, flags=re.IGNORECASE)
    stem = _UNSAFE_NAME.sub("_", base).strip("._")
    return (stem or "document")[:100]


def extraction_path(filename: Optional[str]) -> str:
    return os.path.join(OUTPUT_DIR,
                        f"{output_stem(filename)}.extracted.json")


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def save_extraction(data: dict, filename: Optional[str]) -> str:
    """Write an extraction dict (from doc_to_dict) to
    output/<stem>.extracted.json, and return that path. Each document name
    gets one file, overwritten every run, so the output folder always has
    the latest extraction for each document."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = extraction_path(filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False,
                  default=_json_default)
    return path


def save_extraction_quietly(data: dict, filename: Optional[str]):
    """Same as save_extraction, but a disk error here should never fail
    the whole analysis. Returns the path, or None if the write failed."""
    try:
        return save_extraction(data, filename)
    except OSError as exc:
        log.warning("Could not write extraction output for %r: %s",
                    filename, exc)
        return None


# --------------------------------------------------------------------------
# Stored input - the original uploaded .docx, kept in input/ so a run can be
# reproduced from the exact bytes that produced it. Kept separate from
# output/ on purpose: output/ is just derived data, safe to wipe entirely,
# but input/ holds the only copy of what a user actually sent us.
# --------------------------------------------------------------------------
def source_path(filename: Optional[str]) -> str:
    return os.path.join(INPUT_DIR, f"{output_stem(filename)}.docx")


def save_source(data: bytes, filename: Optional[str]) -> str:
    """Write the uploaded bytes to input/<stem>.docx and return the path.

    Same rule as the extraction output: one file per document name,
    overwritten each run, with the filename sanitised by output_stem() so a
    crafted upload name can't write outside INPUT_DIR. The bytes are
    written exactly as received - this is the original input, not a
    re-saved copy, so the file on disk matches the upload byte for byte.
    """
    os.makedirs(INPUT_DIR, exist_ok=True)
    path = source_path(filename)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def save_source_quietly(data: bytes, filename: Optional[str]):
    """Same as save_source, but a disk error here should never fail
    the whole analysis. Returns the path, or None if the write failed."""
    try:
        return save_source(data, filename)
    except OSError as exc:
        log.warning("Could not write source copy for %r: %s", filename, exc)
        return None
