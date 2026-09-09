"""Rule 7 - Dates near signature blocks.

For each signature block found by rule 6, a date needs to show up close by
- either within a set number of blocks in reading order, or in the same
table row. A date "somewhere in the document" doesn't count.

The evidence says exactly where each date was found, not just that one
exists: a date right on the signature line and a date four paragraphs away
are both accepted, but they're not equally convincing, and a reader should
be able to tell the difference without opening the file. If a block has no
nearby date, the finding also says what range was actually searched.
"""
from __future__ import annotations

from typing import Optional

from app.extractor import Doc, Paragraph
from .base import (
    Rule,
    RuleConfig,
    Finding,
    Locator,
    signature_paragraphs,
    find_dates,
    find_revision_table,
)


class Rule07(Rule):
    id = 7
    name = "Dates near signatures"
    severity = "warning"
    description = ("Each signature block must have a date within a bounded "
                   "window of flow-order blocks or in the same table row.")

    def evaluate(self, doc: Doc, config: RuleConfig) -> Finding:
        sig_paras = signature_paragraphs(doc)
        if not sig_paras:
            return self.fail(
                "No signature blocks found, so no signature carries a date.")

        loc = Locator(doc)
        flow = doc.flow_ordered()
        pos_by_index = {p.block_index: i for i, p in enumerate(flow)}
        window = max(1, config.date_window)

        # dates in the revision history are about past changes, not about
        # when someone actually signed - and a long revision table can end
        # close enough to an approval block below it to get mixed up with it
        revision = find_revision_table(doc)
        skip = ({p.block_index for p in revision.iter_paragraphs()}
                if revision is not None else set())

        dated: list[str] = []
        undated: list[str] = []
        evidence: list[str] = []

        for sig in sig_paras:
            found = self._nearby_date(doc, sig, flow, pos_by_index, window,
                                      skip, loc)
            if found:
                date_text, where = found
                dated.append(sig.location)
                evidence.append(loc.describe(
                    sig, f"dated {date_text}, found {where}"))
            else:
                undated.append(sig.location)
                evidence.append(loc.describe(
                    sig, "no date on the line, in the same table row, or "
                         f"within {window} block(s) either side"))

        if undated:
            return self.fail(
                f"{len(undated)} of {len(sig_paras)} signature block(s) have "
                "no nearby date.",
                evidence=evidence, locations=undated, confidence="heuristic")
        return self.ok(
            f"All {len(dated)} signature block(s) have a nearby date.",
            evidence=evidence, locations=dated, confidence="heuristic")

    def _nearby_date(self, doc: Doc, sig: Paragraph, flow: list[Paragraph],
                     pos_by_index: dict, window: int, skip: set,
                     loc: Locator) -> Optional[tuple[str, str]]:
        """The date that belongs to this signature, and where it was found."""
        # check the signature line's own text first
        hits = find_dates(sig.text)
        if hits:
            return hits[0][0], "on the signature line itself"
        # then the rest of the same table row
        if sig.in_table and sig.table_pos is not None:
            t, r, _ = sig.table_pos
            if t < len(doc.tables):
                row = doc.tables[t].rows[r]
                for c, cell in enumerate(row.cells):
                    ch = find_dates(cell.text())
                    if ch:
                        return ch[0][0], (f"in the same table row "
                                          f"(Table {t + 1}, row {r + 1}, "
                                          f"cell {c + 1})")
        # finally, look at the nearby paragraphs within the window
        pos = pos_by_index.get(sig.block_index)
        if pos is not None:
            lo = max(0, pos - window)
            hi = min(len(flow), pos + window + 1)
            # check the closest paragraphs first, not just the earliest ones
            for i in sorted(range(lo, hi), key=lambda i: (abs(i - pos), i)):
                p = flow[i]
                if p is sig or p.block_index in skip:
                    continue
                ch = find_dates(p.text)
                if ch:
                    return ch[0][0], f"in {loc.where(p)}"
        return None


RULE = Rule07()
