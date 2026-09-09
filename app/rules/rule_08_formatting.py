"""Rule 8 - Font and spacing consistency.

Works out the document's dominant body font, size and spacing by looking at
body paragraphs, weighted by how many characters use each value, then flags
any body paragraph that doesn't match. Headings, captions, table cells,
list items, and any cover/title-block content before the first heading are
left out of both the baseline and the check. A few bold words inside a
paragraph are fine, since we compare each paragraph's dominant font (the
one most of its characters use) - a whole paragraph set in a different
font is what actually gets flagged.

A cover page's title block (the document title, subtitle, company name
above the first section heading) is deliberately styled differently from
the body -- that is not a formatting defect, so those paragraphs never
enter the baseline or get flagged.

Small spacing differences (a couple of points of paragraph spacing, a
fraction of a point of font size) are typical Word noise rather than a
real inconsistency, so comparisons tolerate a small gap instead of
flagging any non-exact match.

The baseline is always reported, pass or fail. Just saying "size 14.0 vs
11.0" doesn't tell you which one is correct, so the evidence always names
the document's own dominant value, quotes the paragraph that's different,
and says which section it's in.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from app.extractor import Doc, Paragraph
from .base import Rule, RuleConfig, Finding, Locator, heading_level, iter_headings


MIN_BASELINE_PARAS = 3

# Tolerances below which a difference is Word noise, not a real deviation.
SIZE_TOLERANCE = 0.5       # pt
LINE_SPACING_TOLERANCE = 0.05
PARA_SPACING_TOLERANCE = 3.0  # pt, e.g. "space after" / "space before"

# Word's own constants (LEFT, CENTER, ...) look like shouting in a report,
# so these map them to normal words instead.
_ALIGNMENT_WORDS = {
    "LEFT": "left-aligned",
    "RIGHT": "right-aligned",
    "CENTER": "centred",
    "JUSTIFY": "justified",
}


def _differs(value: Optional[float], base: Optional[float],
             tolerance: float = 0.0) -> bool:
    """True if value and base disagree by more than tolerance. None only
    equals None -- an explicit value next to an inherited one is a real
    difference, however small the number involved."""
    if value is None or base is None:
        return value != base
    return abs(value - base) > tolerance


def _first_heading_index(doc: Doc) -> Optional[int]:
    return next((h.block_index for h in iter_headings(doc)), None)


def _is_caption(p: Paragraph) -> bool:
    sid = (p.props.style_id or "").lower()
    name = (p.props.style_name or "").lower()
    return "caption" in sid or "caption" in name


def _selected(p: Paragraph, cover_cutoff: Optional[int]) -> bool:
    if p.in_table or p.from_textbox:
        return False
    if heading_level(p) is not None:
        return False
    if p.props.is_list or _is_caption(p):
        return False
    if cover_cutoff is not None and p.block_index < cover_cutoff:
        return False
    return p.word_count() >= 3


def _weighted_mode(counter: Counter):
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _para_family(p: Paragraph) -> Optional[str]:
    c: Counter = Counter()
    for r in p.runs:
        if r.text.strip() and r.font.name:
            c[r.font.name] += len(r.text)
    return _weighted_mode(c)


def _para_size(p: Paragraph) -> Optional[float]:
    c: Counter = Counter()
    for r in p.runs:
        if r.text.strip() and r.font.size is not None:
            c[r.font.size] += len(r.text)
    return _weighted_mode(c)


def _r(value):
    """Round a number so float comparisons are stable. None stays None."""
    if value is None:
        return None
    return round(float(value), 2)


# --------------------------------------------------------------------------
# formatting numbers for the report
# --------------------------------------------------------------------------
def _num(value) -> str:
    """A number without an unnecessary trailing '.0'."""
    return f"{value:g}"


def _pt(value) -> str:
    """Format a value in points, or "inherited" if it's None - meaning the
    paragraph didn't set anything itself and just used whatever its style
    gave it, which isn't the same thing as an actual 0."""
    return "inherited" if value is None else f"{_num(value)}pt"


def _spacing(value) -> str:
    return "inherited" if value is None else f"{_num(value)}"


def _align(value) -> str:
    key = value or "LEFT"
    return _ALIGNMENT_WORDS.get(key, key.lower())


def _instead(what: str, mine: str, base: str) -> str:
    return f"{what} {mine} instead of {base}"


class Rule08(Rule):
    id = 8
    name = "Font and spacing consistency"
    severity = "warning"
    description = ("Body paragraphs should share one font family, size, line "
                   "spacing, paragraph spacing and alignment.")

    def evaluate(self, doc: Doc, config: RuleConfig) -> Finding:
        cover_cutoff = _first_heading_index(doc)
        paras = [p for p in doc.body_paragraphs() if _selected(p, cover_cutoff)]
        if len(paras) < MIN_BASELINE_PARAS:
            return self.fail(
                f"Only {len(paras)} body paragraph(s) -- too few to establish "
                "a formatting baseline, so the document has almost no body "
                "text to be consistent about.")

        loc = Locator(doc)
        fam_c: Counter = Counter()
        size_c: Counter = Counter()
        ls_c: Counter = Counter()
        sb_c: Counter = Counter()
        sa_c: Counter = Counter()
        align_c: Counter = Counter()

        for p in paras:
            chars = len(p.text)
            for r in p.runs:
                if r.text.strip() and r.font.name:
                    fam_c[r.font.name] += len(r.text)
                if r.text.strip() and r.font.size is not None:
                    size_c[r.font.size] += len(r.text)
            ls_c[_r(p.props.line_spacing)] += chars
            sb_c[_r(p.props.space_before)] += chars
            sa_c[_r(p.props.space_after)] += chars
            align_c[p.props.alignment or "LEFT"] += chars

        base_family = _weighted_mode(fam_c)
        base_size = _weighted_mode(size_c)
        base_ls = _weighted_mode(ls_c)
        base_sb = _weighted_mode(sb_c)
        base_sa = _weighted_mode(sa_c)
        base_align = _weighted_mode(align_c)

        baseline = (
            f"{base_family or 'unnamed font'}, {_pt(base_size)}, "
            f"line spacing {_spacing(base_ls)}, "
            f"space before {_pt(base_sb)}, space after {_pt(base_sa)}, "
            f"{_align(base_align)}")
        header = [
            f"The document's own body style: {baseline}.",
            f"Compared {len(paras)} body paragraph(s); headings, list items, "
            "captions, text boxes, table cells and any cover/title-block "
            "content before the first heading are excluded.",
        ]

        evidence: list[str] = []
        locations: list[str] = []

        for p in paras:
            deviations = []
            fam = _para_family(p)
            if base_family and fam and fam != base_family:
                deviations.append(_instead("font", fam, base_family))
            size = _para_size(p)
            if base_size and size and _differs(size, base_size, SIZE_TOLERANCE):
                deviations.append(_instead("size", _pt(size), _pt(base_size)))
            if base_ls is not None and _differs(
                    _r(p.props.line_spacing), base_ls, LINE_SPACING_TOLERANCE):
                deviations.append(_instead(
                    "line spacing", _spacing(_r(p.props.line_spacing)),
                    _spacing(base_ls)))
            if _differs(_r(p.props.space_before), base_sb,
                        PARA_SPACING_TOLERANCE):
                deviations.append(_instead(
                    "space before", _pt(_r(p.props.space_before)),
                    _pt(base_sb)))
            if _differs(_r(p.props.space_after), base_sa,
                        PARA_SPACING_TOLERANCE):
                deviations.append(_instead(
                    "space after", _pt(_r(p.props.space_after)), _pt(base_sa)))
            if (p.props.alignment or "LEFT") != base_align:
                deviations.append(_instead(
                    "alignment", _align(p.props.alignment),
                    _align(base_align)))
            if deviations:
                evidence.append(loc.describe(p, "; ".join(deviations)))
                locations.append(p.location)

        if locations:
            return self.fail(
                f"{len(locations)} of {len(paras)} body paragraph(s) deviate "
                "from the document's own body style.",
                evidence=header + evidence, locations=locations,
                confidence="heuristic")
        return self.ok(
            f"All {len(paras)} body paragraphs share one body style.",
            evidence=header, confidence="heuristic")


RULE = Rule08()
