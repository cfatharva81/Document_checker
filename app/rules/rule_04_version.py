"""Rule 4 - Version number present.

The document needs to state a version number somewhere a reader can find
it: in the body, a header or footer, a document-info table, the revision
history, or the file's own metadata. Every place a version shows up gets
reported, so the finding also works as a map of where it's declared.

This rule only checks that a version exists - it does not check that all
the versions agree with each other. A document with "1.1" in the header
and "1.2" in the body still passes. Whether those two should match is a
different question, and this rule doesn't try to answer it.
"""
from __future__ import annotations

import re

from app.extractor import Doc, Table
from .base import (
    Rule, RuleConfig, Finding, Locator, dedupe, find_revision_table,
    find_versions, header_column_index, table_labeled_values,
)


# In a table, a version is often just a bare number sitting in its own
# cell, with the word "Version" as the label in a different cell or column
# header. The regex in find_versions() looks for both together in one bit
# of text, so it would never catch this - hence the separate handling here.
_VERSION_LABEL = re.compile(
    r"^(?:version|revision|rev)\.?(?:\s*(?:no|number|#))?\.?$", re.IGNORECASE)
_VERSION_VALUE = re.compile(r"^v?\.?\s*(\d+(?:\.\d+){0,3})$", re.IGNORECASE)

# shown back to the reader when nothing is found, so "no version found"
# also says exactly where we looked
SEARCHED = ("Searched: every body paragraph and table cell, every header and "
            "footer, 'Version | 2.1' style table rows, the revision history, "
            "and the file's subject and keywords.")


def _version_key(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def _bare_version(text: str):
    """'2.1' or 'v2.1' -> '2.1'; anything else -> None."""
    m = _VERSION_VALUE.match(text.strip())
    return m.group(1) if m else None


def _column_versions(table: Table) -> list[str]:
    """Version numbers from the version column of a revision table."""
    col = header_column_index(table, _VERSION_LABEL)
    if col is None:
        return []
    out = []
    for row in table.rows[1:]:
        if col < len(row.cells):
            v = _bare_version(row.cells[col].text())
            if v:
                out.append(v)
    return out


def _phrase(versions: list[str]) -> str:
    """'Version 1.2' for one, 'Versions 1.1 and 1.2' for several."""
    if len(versions) == 1:
        return f"Version {versions[0]}"
    return "Versions " + ", ".join(versions[:-1]) + f" and {versions[-1]}"


class Rule04(Rule):
    id = 4
    name = "Version number present"
    severity = "warning"
    description = ("The document must state a version number somewhere -- in "
                   "the body, a header or footer, a document-information "
                   "table, the revision history, or the file metadata.")

    def evaluate(self, doc: Doc, config: RuleConfig) -> Finding:
        loc = Locator(doc)
        table = find_revision_table(doc)
        history_paras = ({p.block_index for p in table.iter_paragraphs()}
                         if table is not None else set())
        history_label = (f"Table {table.table_index + 1}"
                         if table is not None else None)

        # kept separate on purpose: a version in the revision history is
        # what the document used to be, while one stated outside it is
        # what the document currently is
        stated: list[tuple[str, str]] = []
        history: list[tuple[str, str]] = []

        for p in doc.flow_ordered():
            bucket = history if p.block_index in history_paras else stated
            for v in find_versions(p.text):
                bucket.append((v, loc.where(p)))

        for hf in doc.all_headers() + doc.all_footers():
            for v in find_versions(hf.text()):
                stated.append((v, hf.location))

        # a "Version | 2.1" row in a document-info table states the current
        # version, with the label and value in separate cells
        for value, where in table_labeled_values(doc, _VERSION_LABEL):
            bare = _bare_version(value)
            if bare is None:
                continue
            bucket = history if where == history_label else stated
            bucket.append((bare, where))

        if table is not None:
            for v in _column_versions(table):
                history.append((v, loc.table(table)))

        for label, value in (("subject", doc.core.subject),
                             ("keywords", doc.core.keywords)):
            if value:
                for v in find_versions(value):
                    stated.append((v, f"File metadata ({label})"))

        filename_versions = find_versions(doc.filename)
        if filename_versions and not any(
                v == stated_v for v in filename_versions
                for stated_v, _ in stated):
            evidence = dedupe(
                [f"Version {v} — {w}" for v, w in stated]
                + [f"Version {v} — {w} (revision history)"
                   for v, w in history])
            return self.fail(
                f"File name version {filename_versions[0]} is not stated "
                "in the document.",
                evidence=evidence + [f"File name: {doc.filename!r}"],
                locations=dedupe([w for _, w in stated] + [w for _, w in history]))

        if not stated and not history:
            return self.fail(
                "No version number is stated anywhere in the document.",
                evidence=[SEARCHED])

        evidence = dedupe(
            [f"Version {v} — {w}" for v, w in stated]
            + [f"Version {v} — {w} (revision history)"
               for v, w in history])
        locations = dedupe([w for _, w in stated] + [w for _, w in history])

        if stated:
            distinct = sorted({v for v, _ in stated}, key=_version_key)
            return self.ok(
                f"{_phrase(distinct)} stated in {len(stated)} place(s) in the "
                "document.",
                evidence=evidence, locations=locations)

        # only found in the revision history - the reader can still find a
        # version number, but the document never states which one is current
        latest = max((v for v, _ in history), key=_version_key)
        return self._make(
            True,
            f"Version {latest} appears in the revision history; the document "
            "states no version outside it.",
            evidence=evidence, locations=locations, confidence="heuristic")


RULE = Rule04()
