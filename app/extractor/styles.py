"""Working out the actual formatting a run or paragraph ends up with.

This is the messiest part of reading a .docx file. Word only records what
each level *changes* - so a run's real font might be set directly on the
run, or on its character style, or on the paragraph style, or somewhere up
the chain of styles it's based on, or in the document-wide defaults, or only
as a reference to the theme. python-docx just gives back None for any of
those inherited cases. StyleResolver walks that whole chain and works out
what the reader of the document would actually see.
"""
from __future__ import annotations

from typing import Optional

from lxml import etree

from .headings import heading_level_from_style
from .model import ParagraphProps, ResolvedFont, StyleIndex, StyleInfo
from .xmlutil import a, as_bool, get, halfpt_to_pt, twips_to_pt, w, wval


_RPR_KEYS = ("font_literal", "font_theme", "size", "bold", "italic",
             "underline", "color")

_PPR_KEYS = ("style_id", "outline_level", "space_before", "space_after",
             "line_spacing", "line_spacing_rule", "alignment",
             "first_line_indent", "left_indent", "right_indent", "is_list")

_ALIGN_MAP = {"both": "JUSTIFY", "distribute": "JUSTIFY", "start": "LEFT",
              "end": "RIGHT", "left": "LEFT", "right": "RIGHT",
              "center": "CENTER"}


def _parse_rpr(rpr: Optional[etree._Element]) -> dict:
    """Read a w:rPr element into a plain dict. Every key is always present,
    set to None if that property wasn't specified."""
    d = dict.fromkeys(_RPR_KEYS)
    if rpr is None:
        return d
    rfonts = rpr.find(w("rFonts"))
    if rfonts is not None:
        d["font_literal"] = (rfonts.get(w("ascii"))
                             or rfonts.get(w("hAnsi")))
        d["font_theme"] = (rfonts.get(w("asciiTheme"))
                           or rfonts.get(w("hAnsiTheme")))
    d["size"] = halfpt_to_pt(wval(rpr.find(w("sz"))))
    d["bold"] = as_bool(rpr.find(w("b")))
    d["italic"] = as_bool(rpr.find(w("i")))
    u = rpr.find(w("u"))
    if u is not None:
        d["underline"] = (wval(u) or "single").lower()
    color = rpr.find(w("color"))
    if color is not None:
        val = wval(color)
        theme = color.get(w("themeColor"))
        if val and val != "auto":
            d["color"] = val.upper()
        elif theme:
            d["color"] = f"theme:{theme}"
        elif val:
            d["color"] = val  # "auto"
    return d


def _parse_ppr(ppr: Optional[etree._Element]) -> dict:
    d = dict.fromkeys(_PPR_KEYS)
    if ppr is None:
        return d
    pstyle = ppr.find(w("pStyle"))
    if pstyle is not None:
        d["style_id"] = wval(pstyle)
    outline = ppr.find(w("outlineLvl"))
    if outline is not None:
        try:
            d["outline_level"] = int(wval(outline))
        except (TypeError, ValueError):
            pass
    spacing = ppr.find(w("spacing"))
    if spacing is not None:
        d["space_before"] = twips_to_pt(spacing.get(w("before")))
        d["space_after"] = twips_to_pt(spacing.get(w("after")))
        line = spacing.get(w("line"))
        rule = (spacing.get(w("lineRule")) or "auto").lower()
        if line is not None:
            try:
                line_i = int(line)
            except ValueError:
                line_i = None
            if line_i is not None:
                if rule == "auto":
                    d["line_spacing"] = round(line_i / 240.0, 4)
                    d["line_spacing_rule"] = "AUTO"
                else:
                    d["line_spacing"] = round(line_i / 20.0, 4)
                    d["line_spacing_rule"] = (
                        "EXACT" if rule == "exact" else "AT_LEAST")
    jc = ppr.find(w("jc"))
    if jc is not None:
        d["alignment"] = _map_align(wval(jc))
    ind = ppr.find(w("ind"))
    if ind is not None:
        first = ind.get(w("firstLine"))
        hanging = ind.get(w("hanging"))
        if first is not None:
            d["first_line_indent"] = twips_to_pt(first)
        elif hanging is not None:
            hv = twips_to_pt(hanging)
            d["first_line_indent"] = -hv if hv is not None else None
        left = ind.get(w("left")) or ind.get(w("start"))
        right = ind.get(w("right")) or ind.get(w("end"))
        d["left_indent"] = twips_to_pt(left)
        d["right_indent"] = twips_to_pt(right)
    numpr = ppr.find(w("numPr"))
    if numpr is not None:
        numid = numpr.find(w("numId"))
        if numid is not None and wval(numid) not in (None, "0"):
            d["is_list"] = True
    return d


def _map_align(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val = val.lower()
    return _ALIGN_MAP.get(val, val.upper())


class StyleResolver:
    """Owns styles.xml + theme, resolves run/paragraph formatting."""

    def __init__(self, styles_el: Optional[etree._Element],
                 theme_el: Optional[etree._Element]):
        self._styles: dict[str, dict] = {}
        self._default_para: Optional[str] = None
        self._default_char: Optional[str] = None
        self._docdef_rpr: dict = _parse_rpr(None)
        self._docdef_ppr: dict = _parse_ppr(None)
        self.theme_major: Optional[str] = None
        self.theme_minor: Optional[str] = None
        self._style_caches: dict[str, dict] = {"rpr": {}, "ppr": {}}

        self._load_theme(theme_el)
        self._load_styles(styles_el)

    # ---- loading -----------------------------------------------------
    def _load_theme(self, theme_el: Optional[etree._Element]) -> None:
        if theme_el is None:
            return
        def latin(which: str) -> Optional[str]:
            font = theme_el.find(
                f".//{a('fontScheme')}/{a(which)}/{a('latin')}")
            return font.get("typeface") if font is not None else None
        self.theme_major = latin("majorFont")
        self.theme_minor = latin("minorFont")

    def _load_styles(self, styles_el: Optional[etree._Element]) -> None:
        if styles_el is None:
            return
        docdef = styles_el.find(w("docDefaults"))
        if docdef is not None:
            rprd = get(docdef, "rPrDefault", "rPr")
            pprd = get(docdef, "pPrDefault", "pPr")
            self._docdef_rpr = _parse_rpr(rprd)
            self._docdef_ppr = _parse_ppr(pprd)
        for st in styles_el.findall(w("style")):
            sid = st.get(w("styleId"))
            if not sid:
                continue
            stype = st.get(w("type")) or "paragraph"
            is_default = (st.get(w("default")) or "0") in ("1", "true")
            name_el = st.find(w("name"))
            name = wval(name_el)
            based = wval(st.find(w("basedOn")))
            self._styles[sid] = {
                "id": sid,
                "type": stype,
                "name": name,
                "based_on": based,
                "default": is_default,
                "rpr": _parse_rpr(st.find(w("rPr"))),
                "ppr": _parse_ppr(st.find(w("pPr"))),
            }
            if is_default and stype == "paragraph" and not self._default_para:
                self._default_para = sid
            if is_default and stype == "character" and not self._default_char:
                self._default_char = sid

    # ---- style chain merge ------------------------------------------
    def _chain(self, style_id: Optional[str]) -> list[str]:
        """The basedOn chain for a style, ordered from root to this style."""
        seen: list[str] = []
        cur = style_id
        guard = 0
        while cur and cur in self._styles and cur not in seen and guard < 50:
            seen.append(cur)
            cur = self._styles[cur]["based_on"]
            guard += 1
        seen.reverse()
        return seen

    def _merged(self, style_id: Optional[str], which: str) -> dict:
        """Combine a style's whole basedOn chain into one dict. If two
        levels set the same property, the more specific one (further down
        the chain) wins."""
        keys = _RPR_KEYS if which == "rpr" else _PPR_KEYS
        if not style_id or style_id not in self._styles:
            return dict.fromkeys(keys)
        cache = self._style_caches[which]
        if style_id not in cache:
            merged = dict.fromkeys(keys)
            for sid in self._chain(style_id):
                _overlay(merged, self._styles[sid][which])
            cache[style_id] = merged
        return cache[style_id]

    # ---- public resolution ------------------------------------------
    def resolve_font(self, run_rpr: Optional[etree._Element],
                     para_style_id: Optional[str]) -> ResolvedFont:
        direct = _parse_rpr(run_rpr)
        # the character style the run points to, if any
        rstyle_el = run_rpr.find(w("rStyle")) if run_rpr is not None else None
        char_style_id = wval(rstyle_el)

        levels = [
            direct,
            self._merged(char_style_id, "rpr"),
            self._merged(para_style_id or self._default_para, "rpr"),
            self._docdef_rpr,
        ]
        name, is_theme = self._resolve_name(levels)
        return ResolvedFont(
            name=name,
            name_is_theme=is_theme,
            size=_first(levels, "size"),
            bold=_first(levels, "bold"),
            italic=_first(levels, "italic"),
            underline=_first(levels, "underline"),
            color=_first(levels, "color"),
        )

    def _resolve_name(self, levels: list[dict]) -> tuple[Optional[str], bool]:
        for lvl in levels:
            theme_tok = lvl.get("font_theme")
            literal = lvl.get("font_literal")
            if theme_tok:
                resolved = self._theme_font(theme_tok)
                if resolved:
                    return resolved, True
            if literal:
                return literal, False
        return None, False

    def _theme_font(self, token: str) -> Optional[str]:
        t = token.lower()
        if t.startswith("major"):
            return self.theme_major
        if t.startswith("minor"):
            return self.theme_minor
        return None

    def resolve_para(self, ppr_el: Optional[etree._Element]) -> ParagraphProps:
        direct = _parse_ppr(ppr_el)
        style_id = direct.get("style_id") or self._default_para
        style_merged = self._merged(style_id, "ppr")
        levels = [direct, style_merged, self._docdef_ppr]
        style_name = None
        if style_id and style_id in self._styles:
            style_name = self._styles[style_id]["name"]
        heading = heading_level_from_style(style_id, style_name)
        outline = _first(levels, "outline_level")
        if outline is None and heading is not None:
            outline = heading - 1
        return ParagraphProps(
            style_id=style_id,
            style_name=style_name,
            outline_level=outline,
            heading_level=heading,
            space_before=_first(levels, "space_before"),
            space_after=_first(levels, "space_after"),
            line_spacing=_first(levels, "line_spacing"),
            line_spacing_rule=_first(levels, "line_spacing_rule"),
            alignment=_first(levels, "alignment"),
            first_line_indent=_first(levels, "first_line_indent"),
            left_indent=_first(levels, "left_indent"),
            right_indent=_first(levels, "right_indent"),
            is_list=bool(_first(levels, "is_list")),
        )

    # ---- public summary ---------------------------------------------
    def index(self) -> StyleIndex:
        styles = {
            sid: StyleInfo(
                style_id=sid,
                name=info["name"],
                type=info["type"],
                based_on=info["based_on"],
                is_default=info["default"],
            )
            for sid, info in self._styles.items()
        }
        return StyleIndex(
            styles=styles,
            theme_major=self.theme_major,
            theme_minor=self.theme_minor,
            default_para_style=self._default_para,
            default_char_style=self._default_char,
        )


def _overlay(base: dict, over: dict) -> None:
    """Apply non-None values of ``over`` onto ``base`` in place."""
    for k, v in over.items():
        if v is not None:
            base[k] = v


def _first(levels: list[dict], key: str):
    for lvl in levels:
        v = lvl.get(key)
        if v is not None:
            return v
    return None
