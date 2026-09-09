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
    joined = " ".join(headers)
    return bool(_SIG_TABLE_NAME.search(joined)
               and _SIG_TABLE_OTHER.search(joined))


def _columns(table: Table) -> str:
    """The header row as a reader sees it, original casing kept."""
    if not table.rows:
        return ""
    return " | ".join(c.text().strip() for c in table.rows[0].cells)


class Rule06(Rule):
    id = 6
    name = "Signature blocks"
    severity = "error"
    description = ("A 'Prepared/Reviewed/Approved by' block or a "
                   "name/designation/signature/date table must be present.")

    def evaluate(self, doc: Doc, config: RuleConfig) -> Finding:
        loc = Locator(doc)
        sig_paras = signature_paragraphs(doc)
        sig_tables = [t for t in doc.tables if is_signature_table(t)]

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
            rows = max(0, len(t.rows) - 1)
            evidence.append(
                f"{loc.table(t)} — signature table, columns: {_columns(t)} "
                f"({rows} signatory row(s))")
            locations.append(f"Table {t.table_index + 1}")

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
