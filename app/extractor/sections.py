"""Sections and their headers/footers, including "same as previous section".

A section that's linked to the previous one doesn't store its own header or
footer content - the real content lives in an earlier section. Rules 4, 11
and 13 all need to read header/footer text, so we resolve that inheritance
once here instead of making every rule handle it.
"""
from __future__ import annotations

from typing import Optional

from lxml import etree

from .model import HeaderFooter, Paragraph, Section
from .walker import Ctx, walk_container


_HEADER_VARIANTS = (
    ("default", "header"),
    ("first", "first_page_header"),
    ("even", "even_page_header"),
)
_FOOTER_VARIANTS = (
    ("default", "footer"),
    ("first", "first_page_footer"),
    ("even", "even_page_footer"),
)


def build_sections(document, resolver) -> list[Section]:
    sections: list[Section] = []
    prev: Optional[Section] = None
    for i, sec in enumerate(document.sections):
        section = Section(
            index=i,
            different_first_page=bool(sec.different_first_page_header_footer),
        )
        for which, attr in _HEADER_VARIANTS:
            hf = _capture(getattr(sec, attr, None), which, "header",
                          i, resolver, prev)
            if hf is not None:
                section.headers[which] = hf
        for which, attr in _FOOTER_VARIANTS:
            hf = _capture(getattr(sec, attr, None), which, "footer",
                          i, resolver, prev)
            if hf is not None:
                section.footers[which] = hf
        sections.append(section)
        prev = section
    return sections


def _capture(hf_obj, which: str, kind: str, index: int, resolver,
             prev: Optional[Section]) -> Optional[HeaderFooter]:
    if hf_obj is None:
        return None

    linked = bool(getattr(hf_obj, "is_linked_to_previous", False))
    if linked:
        base = _inherit(prev, which, kind)
        if base is None:
            return None
        return HeaderFooter(
            which=which, kind=kind, section_index=index,
            paragraphs=base.paragraphs, fields=base.fields,
            is_linked_to_previous=True,
        )

    root = _root_element(hf_obj)
    if root is None:
        return None

    ctx = Ctx(resolver)
    blocks = walk_container(root, ctx)
    paras: list[Paragraph] = [b for b in blocks if isinstance(b, Paragraph)]
    for table in ctx.tables:
        paras.extend(table.iter_paragraphs())
    fields = [f for p in paras for f in p.fields]

    if not paras and not fields:
        return None
    return HeaderFooter(
        which=which, kind=kind, section_index=index,
        paragraphs=paras, fields=fields, is_linked_to_previous=False,
    )


def _inherit(prev: Optional[Section], which: str, kind: str):
    if prev is None:
        return None
    table = prev.headers if kind == "header" else prev.footers
    return table.get(which) or table.get("default")


def _root_element(hf_obj) -> Optional[etree._Element]:
    """Get the header/footer's root XML element, however we can."""
    el = getattr(hf_obj, "_element", None)
    if el is not None:
        return el
    # fall back: get it from the first paragraph's parent element
    try:
        paras = hf_obj.paragraphs
    except Exception:
        paras = []
    if paras:
        p = getattr(paras[0], "_p", None) or getattr(paras[0], "_element", None)
        if p is not None:
            return p.getparent()
    return None
