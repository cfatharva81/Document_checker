"""Rule 6 - Signature blocks present.

Each piece of evidence names the section a matching block sits under and
quotes the matching line, so a reader can jump straight to it in Word
instead of counting paragraphs. When nothing matches, the finding lists
exactly what was searched for - otherwise "no signature block found" could
easily be read as a bug in the checker instead of a real gap in the
document.
"""
from __future__ import annotations

import re

from app.extractor import Doc, Table
from .base import (
    Rule,
    RuleConfig,
    Finding,
    Locator,
    SIGNATURE_LABEL_RE,
    signature_paragraphs,
    table_header_cells,
    looks_like_revision_table,
    find_dates,
)


_SIG_TABLE_NAME = re.compile(r"\bname\b", re.IGNORECASE)
_SIG_TABLE_OTHER = re.compile(
    r"\b(?:signature|designation|title|role|date)\b", re.IGNORECASE)

LOOKED_FOR = (
    "Looked for: a 'Prepared by' / 'Reviewed by' / 'Approved by' / "
    "'Authorised by' / 'Checked by' / 'Issued by' line, a 'Signature' or "
    "'Signed & date' label, or a table with a Name column alongside "
    "Signature, Designation, Role or Date.")


def is_signature_table(table: Table) -> bool:
    headers = table_header_cells(table)
    if not headers:
        return False
    if looks_like_revision_table(table):
        return False
    joined = " ".join(headers)
    return bool(_SIG_TABLE_NAME.search(joined)
               and _SIG_TABLE_OTHER.search(joined))


def signature_table_name_values(table: Table) -> list[tuple[int, str]]:
    """Return populated name cells from data rows of a signature table."""
    headers = table_header_cells(table)
    name_col = next((i for i, header in enumerate(headers)
                     if _SIG_TABLE_NAME.search(header)), None)
    if name_col is None:
        return []
    values = []
    for row_index, row in enumerate(table.rows[1:], 1):
        if name_col >= len(row.cells):
            continue
        name = row.cells[name_col].text().strip()
        if name and _has_signature_content(name):
            values.append((row_index, name))
    return values


def _columns(table: Table) -> str:
    """The header row as a reader sees it, original casing kept."""
    if not table.rows:
        return ""
    return " | ".join(c.text().strip() for c in table.rows[0].cells)


def _has_signature_content(text: str) -> bool:
    """A label/date alone is not a completed signature block."""
    text = re.sub(r"^\s*(?:prepared|reviewed|approved|authori[sz]ed|"
                  r"checked|issued|verified|released)\s+by\s*[:\-]?",
                  "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*signature\s*[:\-]?", "", text,
                  flags=re.IGNORECASE)
    for date_text, _ in find_dates(text):
        text = text.replace(date_text, "")
    return bool(re.sub(r"[\s:;,.\-_]+", "", text))


class Rule06(Rule):
    id = 6
    name = "Signature blocks"
    severity = "error"
    description = ("A 'Prepared/Reviewed/Approved by' block or a "
                   "name/designation/signature/date table must be present.")

    def evaluate(self, doc: Doc, config: RuleConfig) -> Finding:
        loc = Locator(doc)
        sig_paras = [p for p in signature_paragraphs(doc)
                     if _has_signature_content(p.text)]
        sig_tables = [t for t in doc.tables
                      if is_signature_table(t)
                      and signature_table_name_values(t)]

        evidence: list[str] = []
        locations: list[str] = []

        for p in sig_paras:
            match = SIGNATURE_LABEL_RE.search(p.text)
            label = match.group(0).strip() if match else ""
            evidence.append(loc.describe(
                p, f"matched the label “{label}”" if label
                else "matched a signature label"))
            locations.append(p.location)

        for t in sig_tables:
            named_rows = signature_table_name_values(t)
            for row_index, name in named_rows:
                table_location = f"Table {t.table_index + 1}, row {row_index + 1}"
                evidence.append(
                    f"{table_location} — signature block for {name!r}; "
                    f"columns: {_columns(t)}")
                locations.append(table_location)

        if evidence:
            return self.ok(
                f"Found {len(sig_paras)} signature label(s) and "
                f"{len(sig_tables)} signature table(s).",
                evidence=evidence, locations=locations, confidence="heuristic")

        paragraphs = len(doc.body_paragraphs())
        return self.fail(
            "No signature block (Prepared/Reviewed/Approved by) or "
            "signature table found.",
            evidence=[f"Searched {paragraphs} paragraph(s) and "
                      f"{len(doc.tables)} table(s), including table cells, "
                      "text boxes and every section.",
                      LOOKED_FOR],
            confidence="heuristic")


RULE = Rule06()
