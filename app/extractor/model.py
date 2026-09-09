"""The Doc model - this is the only thing the rules are allowed to see.

Just plain dataclasses here, no lxml, no python-docx, no file I/O. The
extractor fills these in, and app.rules reads them. Keeping this module free
of outside dependencies is what makes it possible to unit test rules against
documents we build by hand, instead of needing a real .docx file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional, Union


# --------------------------------------------------------------------------
# Run-level
# --------------------------------------------------------------------------
@dataclass
class ResolvedFont:
    """Fully-resolved run formatting (after walking the style chain)."""

    name: Optional[str] = None          # resolved typeface, theme-expanded
    size: Optional[float] = None        # points
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[str] = None     # e.g. "single", "none", or None
    color: Optional[str] = None         # "RRGGBB" hex, "auto", or None
    name_is_theme: bool = False         # name came from a theme font ref

    def key(self) -> tuple:
        """A tuple to compare two runs' formatting, or check if they can merge."""
        return (self.name, self.size, self.bold, self.italic,
                self.underline, self.color)


@dataclass
class Run:
    text: str
    font: ResolvedFont


@dataclass
class Field:
    """A field code, whether complex (w:fldChar) or simple (w:fldSimple)."""

    kind: str            # first instruction token upper-cased: PAGE, NUMPAGES...
    instruction: str     # full instruction text
    result: str          # cached result text (may be empty)
    simple: bool         # True => w:fldSimple


# --------------------------------------------------------------------------
# Paragraph-level
# --------------------------------------------------------------------------
@dataclass
class ParagraphProps:
    """How a paragraph is formatted: style, spacing, indents, alignment."""

    style_id: Optional[str] = None
    style_name: Optional[str] = None
    outline_level: Optional[int] = None      # 0-based; None = body text
    heading_level: Optional[int] = None      # 1..9 or None
    space_before: Optional[float] = None     # points
    space_after: Optional[float] = None      # points
    line_spacing: Optional[float] = None     # multiple (auto) or points
    line_spacing_rule: Optional[str] = None  # AUTO | EXACT | AT_LEAST
    alignment: Optional[str] = None          # LEFT | CENTER | RIGHT | JUSTIFY
    first_line_indent: Optional[float] = None  # points (negative => hanging)
    left_indent: Optional[float] = None
    right_indent: Optional[float] = None
    is_list: bool = False
    in_table: bool = False
    # a guess, not something Word actually recorded. Only set for documents
    # that used bold/font-size tricks instead of real heading styles - see
    # infer_heading_levels()
    inferred_heading_level: Optional[int] = None


@dataclass
class Paragraph:
    """What a paragraph contains, and how it's formatted."""

    block_index: int
    text: str
    runs: list[Run]
    props: ParagraphProps
    fields: list[Field] = field(default_factory=list)
    in_table: bool = False
    from_textbox: bool = False
    # (table_index, row, col) when this paragraph lives inside a table cell
    table_pos: Optional[tuple[int, int, int]] = None
    location: str = ""
    kind: str = "paragraph"

    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class TableRef:
    """Marker occupying a table's slot in the top-level flow."""

    block_index: int
    table_index: int
    location: str = ""
    kind: str = "table"


Block = Union[Paragraph, TableRef]


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------
@dataclass
class Cell:
    blocks: list[Block] = field(default_factory=list)

    def paragraphs(self) -> list[Paragraph]:
        return [b for b in self.blocks if isinstance(b, Paragraph)]

    def text(self) -> str:
        return "\n".join(p.text for p in self.paragraphs())


@dataclass
class Row:
    cells: list[Cell] = field(default_factory=list)


@dataclass
class Table:
    table_index: int
    block_index: int
    rows: list[Row] = field(default_factory=list)

    def iter_paragraphs(self) -> Iterable[Paragraph]:
        for row in self.rows:
            for cell in row.cells:
                for b in cell.blocks:
                    if isinstance(b, Paragraph):
                        yield b


# --------------------------------------------------------------------------
# Sections / headers / footers
# --------------------------------------------------------------------------
@dataclass
class HeaderFooter:
    which: str               # "default" | "first" | "even"
    kind: str                # "header" | "footer"
    section_index: int
    paragraphs: list[Paragraph] = field(default_factory=list)
    fields: list[Field] = field(default_factory=list)
    is_linked_to_previous: bool = False

    def text(self) -> str:
        return "\n".join(p.text for p in self.paragraphs)

    @property
    def location(self) -> str:
        label = self.kind.capitalize()
        if self.which != "default":
            label = f"{self.which.capitalize()}-page {self.kind}"
        return f"{label}, section {self.section_index + 1}"


@dataclass
class Section:
    index: int
    different_first_page: bool = False
    headers: dict[str, HeaderFooter] = field(default_factory=dict)
    footers: dict[str, HeaderFooter] = field(default_factory=dict)

    def all_headers(self) -> list[HeaderFooter]:
        return list(self.headers.values())

    def all_footers(self) -> list[HeaderFooter]:
        return list(self.footers.values())


# --------------------------------------------------------------------------
# Document-level
# --------------------------------------------------------------------------
@dataclass
class CoreProps:
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[str] = None
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    last_modified_by: Optional[str] = None


@dataclass
class HeadingEntry:
    level: int          # heading level (1..9)
    text: str
    block_index: int
    location: str


@dataclass
class StyleInfo:
    style_id: str
    name: Optional[str]
    type: str                       # paragraph | character | table | numbering
    based_on: Optional[str] = None
    is_default: bool = False


@dataclass
class StyleIndex:
    """Read-only summary of the style tree, handed to the rules."""

    styles: dict[str, StyleInfo] = field(default_factory=dict)
    theme_major: Optional[str] = None
    theme_minor: Optional[str] = None
    default_para_style: Optional[str] = None
    default_char_style: Optional[str] = None


@dataclass
class Doc:
    filename: str
    core: CoreProps
    blocks: list[Block]            # top-level flow order
    tables: list[Table]
    sections: list[Section]
    styles: StyleIndex

    # ------------------------------------------------------------------
    # Flow-order helpers (rule 7 leans on these)
    # ------------------------------------------------------------------
    def iter_paragraphs(self) -> Iterable[Paragraph]:
        """Every body paragraph in reading order, including table cells,
        text boxes and nested tables. Does not include headers/footers."""
        yield from iter_block_paragraphs(self.blocks, self.tables)

    def body_paragraphs(self) -> list[Paragraph]:
        return list(self.iter_paragraphs())

    def flow_ordered(self) -> list[Paragraph]:
        """Same paragraphs, sorted by block_index."""
        return sorted(self.iter_paragraphs(), key=lambda p: p.block_index)

    def all_headers(self) -> list[HeaderFooter]:
        out: list[HeaderFooter] = []
        for s in self.sections:
            out.extend(s.all_headers())
        return out

    def all_footers(self) -> list[HeaderFooter]:
        out: list[HeaderFooter] = []
        for s in self.sections:
            out.extend(s.all_footers())
        return out


def iter_block_paragraphs(blocks: list[Block],
                          tables: list[Table]) -> Iterable[Paragraph]:
    by_index = {t.table_index: t for t in tables}
    for b in blocks:
        if isinstance(b, Paragraph):
            yield b
        elif isinstance(b, TableRef):
            table = by_index.get(b.table_index)
            if table is None:
                continue
            for row in table.rows:
                for cell in row.cells:
                    yield from iter_block_paragraphs(cell.blocks, tables)

