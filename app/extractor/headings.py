"""Working out heading levels, from Word's own data or from guessing.

Two ways to get a heading level. heading_level_from_style() just reads what
Word recorded. infer_heading_levels() is a fallback for documents that never
used real heading styles - it guesses structure from how text looks. It only
runs when Word recorded nothing at all, so a properly styled document is
always trusted over a guess.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from .model import Block, Paragraph, Table, iter_block_paragraphs


_HEADING_RE = re.compile(r"^\s*heading\s*([1-9])\s*$", re.IGNORECASE)


def heading_level_from_style(style_id: Optional[str],
                             style_name: Optional[str]) -> Optional[int]:
    for candidate in (style_name, style_id):
        if not candidate:
            continue
        m = _HEADING_RE.match(candidate)
        if m:
            return int(m.group(1))
        # style ids look like "Heading3", no space before the number
        m2 = re.match(r"^heading([1-9])$", candidate, re.IGNORECASE)
        if m2:
            return int(m2.group(1))
    return None


# A lot of real SOPs never use Word's heading styles - the author just makes
# a line bold and bumps up the font size instead. Word doesn't record any
# heading info for those lines, so without this the whole document would
# look like one flat block of text to the rules. This function tries to
# recover that structure by looking at how paragraphs actually appear -
# but only if the document has no heading info anywhere, so a properly
# styled document is never overridden.
_SENTENCE_END = re.compile(r"[.;,!?]\s*$")
MAX_HEADING_WORDS = 12
MIN_PARAS_TO_INFER = 4
# bold only looks like a heading signal if it's rare. If most of the
# document is bold, being bold doesn't mean anything special anymore.
BOLD_SIGNAL_MAX_SHARE = 0.4


def _char_weighted_size(paras: list["Paragraph"]) -> Optional[float]:
    counter: Counter = Counter()
    for p in paras:
        for r in p.runs:
            if r.text.strip() and r.font.size is not None:
                counter[r.font.size] += len(r.text)
    return counter.most_common(1)[0][0] if counter else None


def _para_size(p: "Paragraph") -> Optional[float]:
    return _char_weighted_size([p])


def _para_is_bold(p: "Paragraph") -> bool:
    """True if most of the paragraph's visible text is bold."""
    bold = plain = 0
    for r in p.runs:
        n = len(r.text.strip())
        if not n:
            continue
        if r.font.bold:
            bold += n
        else:
            plain += n
    return bold > plain


def infer_heading_levels(blocks: list[Block], tables: list[Table]) -> None:
    """Fill in inferred_heading_level for paragraphs that look like headings:
    short, not a full sentence, and either bigger than the body text or bold
    while bold is still rare. Heading levels are assigned by ranking the
    different font sizes found - the biggest size becomes level 1, the next
    becomes level 2, and so on."""
    everything = list(iter_block_paragraphs(blocks, tables))
    if any(p.props.heading_level is not None or p.props.outline_level is not None
           for p in everything):
        return                      # Word already recorded its own structure

    body = [p for p in everything
            if not p.in_table and not p.from_textbox and p.text.strip()]
    if len(body) < MIN_PARAS_TO_INFER:
        return

    body_size = _char_weighted_size(body)
    bold_share = sum(1 for p in body if _para_is_bold(p)) / len(body)
    bold_is_signal = bold_share <= BOLD_SIGNAL_MAX_SHARE

    candidates: list[tuple[Paragraph, Optional[float]]] = []
    for p in body:
        text = p.text.strip()
        if p.props.is_list or len(text.split()) > MAX_HEADING_WORDS:
            continue
        if _SENTENCE_END.search(text):
            continue
        size = _para_size(p)
        larger = (size is not None and body_size is not None
                  and size > body_size)
        if larger or (bold_is_signal and _para_is_bold(p)):
            candidates.append((p, size))
    if not candidates:
        return

    ranked = sorted({s for _, s in candidates if s is not None}, reverse=True)
    for para, size in candidates:
        level = ranked.index(size) + 1 if size in ranked else len(ranked) + 1
        para.props.inferred_heading_level = min(level, 9)
