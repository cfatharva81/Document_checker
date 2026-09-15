"""Rule 2 - Author name and role."""
from __future__ import annotations

import re

from app.extractor import Doc
from .base import (
    Rule,
    RuleConfig,
    Finding,
    find_revision_table,
    header_column_index,
    normalize_key,
    table_labeled_values,
    table_header_cells,
)


_AUTHOR_LINE_RE = re.compile(
    r"^\s*(?:author|prepared by|owner|document owner|written by|created by)\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
_ROLE_RE = re.compile(
    r"\b(?:author|owner|manager|engineer|officer|lead|head|director|"
    r"coordinator|specialist|analyst|administrator|role|designation|title)\b",
    re.IGNORECASE,
)
_AUTHOR_HDR = re.compile(r"\b(?:author|prepared|owner|name)\b", re.IGNORECASE)
# label cells in a document-information table, where the name sits in the
# next cell rather than after a colon
_AUTHOR_LABEL = re.compile(
    r"^(?:author|prepared\s+by|document\s+owner|owner|written\s+by|"
    r"created\s+by)$", re.IGNORECASE)
_ROLE_LABEL = re.compile(
    r"^(?:role|designation|position|job\s+title)$", re.IGNORECASE)
_APPROVER_LABEL = re.compile(
    r"^(?:approver|approved\s+by|authori[sz]ed\s+by|prepared\s+by)$",
    re.IGNORECASE)
_APPROVER_SECTION = re.compile(r"^approver(?:s)?(?:\s*\(s\))?\s*$",
                               re.IGNORECASE)
_APPROVER_HDR = re.compile(r"\b(?:approv(?:er|ed|al)|authorized|authorised)\b",
                           re.IGNORECASE)
_NAME_HDR = re.compile(
    r"\b(?:name|author|approver|approved\s+by|person|employee)\b",
    re.IGNORECASE)


class Rule02(Rule):
    id = 2
    name = "Author name and role"
    severity = "error"
    description = ("Author metadata (and a named author near the top or in "
                   "the revision table) must be present and not a default "
                   "value like 'User' or 'Administrator'.")

    def _is_default(self, name: str, config: RuleConfig) -> bool:
        key = normalize_key(name)
        return (key in {normalize_key(d) for d in config.default_authors}
                or key.endswith(" user"))

    def _person_name(self, value: str) -> str:
        """Take the person field when a table cell includes role details."""
        return re.split(r"\s*[/|]\s*", value.strip(), maxsplit=1)[0].strip()

    def evaluate(self, doc: Doc, config: RuleConfig) -> Finding:
        evidence: list[str] = []
        locations: list[str] = []
        valid_names: list[str] = []

        for label, value in (("core author", doc.core.author),
                             ("last modified by", doc.core.last_modified_by)):
            if value:
                if self._is_default(value, config):
                    evidence.append(
                        f"{label}: {value!r} (ignored: generic or "
                        "tool-generated name)")
                else:
                    evidence.append(f"{label}: {value!r}")
                    valid_names.append(value)
            else:
                evidence.append(f"{label}: (empty)")

        # author/role line near the top of the document
        role_signal = False
        for p in doc.flow_ordered()[:25]:
            m = _AUTHOR_LINE_RE.match(p.text)
            if m and m.group(1).strip():
                valid_names.append(m.group(1).strip())
                evidence.append(f"author line: {p.text.strip()!r}")
                locations.append(p.location)
            if _ROLE_RE.search(p.text):
                role_signal = True

        # document-information table: 'Author | John Smith', 'Role | ...'
        for value, loc in table_labeled_values(doc, _AUTHOR_LABEL):
            evidence.append(f"document-information author: {value!r}")
            if not self._is_default(value, config):
                valid_names.append(value)
                locations.append(loc)
        for value, loc in table_labeled_values(doc, _ROLE_LABEL):
            role_signal = True
            evidence.append(f"document-information role: {value!r}")

        for value, loc in table_labeled_values(doc, _APPROVER_LABEL):
            name = self._person_name(value)
            role_signal = True
            evidence.append(f"approvers-table author: {name!r} ({loc})")
            if name and not self._is_default(name, config):
                valid_names.append(name)
                locations.append(loc)

        # Approver/sign-off tables are another valid source of the document
        # author. The person may be under either "Approver"/"Approved by"
        # directly or a separate "Name" column.
        prior_paragraphs = doc.flow_ordered()
        for table in doc.tables:
            headers = table_header_cells(table)
            joined = " ".join(headers)
            in_approver_section = any(
                p.block_index < table.block_index
                and _APPROVER_SECTION.fullmatch(p.text.strip())
                for p in prior_paragraphs)
            if not (_APPROVER_HDR.search(joined) or in_approver_section):
                continue
            name_columns = [i for i, header in enumerate(headers)
                            if _NAME_HDR.search(header)]
            if not name_columns:
                continue
            role_signal = True
            for name_col in name_columns:
                for row in table.rows[1:]:
                    if name_col >= len(row.cells):
                        continue
                    raw_name = row.cells[name_col].text().strip()
                    name = self._person_name(raw_name)
                    if name and not _APPROVER_LABEL.fullmatch(name):
                        evidence.append(
                            f"approvers-table author: {name!r} "
                            f"(Table {table.table_index + 1})")
                        if not self._is_default(name, config):
                            valid_names.append(name)
                            locations.append(f"Table {table.table_index + 1}")

        # Keep revision history as an additional author source.
        table = find_revision_table(doc)
        if table is not None:
            col = header_column_index(table, _AUTHOR_HDR)
            if col is not None:
                for row in table.rows[1:]:
                    if col < len(row.cells):
                        raw_name = row.cells[col].text().strip()
                        name = self._person_name(raw_name)
                        if name and not self._is_default(name, config):
                            valid_names.append(name)
                            evidence.append(f"revision-table author: {name!r}")

        valid_names = [n for n in valid_names if n.strip()]
        if valid_names:
            msg = "A named author is present"
            if not role_signal:
                msg += " (no explicit role/designation found)"
            return self._make(True, msg + ".", evidence=evidence,
                              locations=locations, confidence="heuristic")

        return self.fail(
            "No valid author found: metadata is empty or a default value "
            "and no author line, information-table author, revision-table "
            "author, or approver-table author is present.",
            evidence=evidence, locations=locations, confidence="heuristic")


RULE = Rule02()
