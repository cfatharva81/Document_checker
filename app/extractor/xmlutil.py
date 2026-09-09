"""Low-level helpers for reading OOXML: namespaced tags, attribute values,
and unit conversion.

This is the bottom layer of the extractor - everything else in this package
writes w("p") instead of typing out the full namespaced tag name by hand.
"""
from __future__ import annotations

from typing import Optional

from lxml import etree


# the main Word namespace: paragraphs (w:p), runs (w:r), text (w:t), etc.
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"

WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
V = "urn:schemas-microsoft-com:vml"

NS = {"w": W, "a": A, "wp": WP, "r": R, "v": V}


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


def a(tag: str) -> str:
    return f"{{{A}}}{tag}"


def local(el: etree._Element) -> str:
    """Local tag name without namespace."""
    tag = el.tag
    if isinstance(tag, str) and "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag if isinstance(tag, str) else ""


def wval(el: Optional[etree._Element], default=None) -> Optional[str]:
    """Return the ``w:val`` attribute of an element, or default."""
    if el is None:
        return default
    v = el.get(w("val"))
    return v if v is not None else default


def get(parent: Optional[etree._Element], *tags: str) -> Optional[etree._Element]:
    """Chase a path of ``w:`` child tags, returning the leaf or None."""
    cur = parent
    for tag in tags:
        if cur is None:
            return None
        cur = cur.find(w(tag))
    return cur


def as_bool(el: Optional[etree._Element]) -> Optional[bool]:
    """Interpret an on/off toggle element (w:b, w:i, ...).

    Present with no val, or val in {1,true,on} => True.
    val in {0,false,off} => False. Absent => None.
    """
    if el is None:
        return None
    v = el.get(w("val"))
    if v is None:
        return True
    return v.lower() in ("1", "true", "on")


def twips_to_pt(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return int(value) / 20.0
    except (TypeError, ValueError):
        return None


def halfpt_to_pt(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return int(value) / 2.0
    except (TypeError, ValueError):
        return None

