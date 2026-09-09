"""Walks through the document's XML and produces a list of blocks in
reading order.

This is one recursive pass over the body, table cells, text boxes and
content controls. It gives every paragraph and table a stable block_index
that reflects the actual reading order. python-docx can't do this on its
own - its .paragraphs list skips table content entirely and doesn't show
how paragraphs and tables interleave.
"""
from __future__ import annotations

from typing import Optional

from lxml import etree

from .fields import FieldCollector
from .model import (
    Block, Cell, Paragraph, ResolvedFont, Row, Run, Table, TableRef,
)
from .styles import StyleResolver
from .xmlutil import local, w


# ========================================================================
# Run merging
# ========================================================================
def merge_runs(runs: list[Run]) -> list[Run]:
    merged: list[Run] = []
    for run in runs:
        if run.text == "":
            # skip empty runs, but don't let them break up a merge that's
            # already in progress
            if merged:
                merged[-1] = Run(text=merged[-1].text, font=merged[-1].font)
            continue
        if merged and merged[-1].font.key() == run.font.key():
            merged[-1] = Run(text=merged[-1].text + run.text, font=merged[-1].font)
        else:
            merged.append(Run(text=run.text, font=run.font))
    return merged


# ========================================================================
# Walk state
# ========================================================================
class Ctx:
    """Shared state for one walk: the running block counter and the list
    of tables found so far."""

    def __init__(self, resolver: StyleResolver):
        self.resolver = resolver
        self.tables: list[Table] = []
        self._counter = -1

    def next_index(self) -> int:
        self._counter += 1
        return self._counter


# --------------------------------------------------------------------------
# Block-level walk
# --------------------------------------------------------------------------
def walk_container(container: etree._Element, ctx: Ctx,
                   in_table: bool = False,
                   table_pos: Optional[tuple] = None,
                   from_textbox: bool = False) -> list[Block]:
    """Walk one container: could be the body, a table cell, a content
    control's content, or a header/footer."""
    blocks: list[Block] = []
    for child in container:
        tag = local(child)
        if tag == "p":
            idx = ctx.next_index()
            para, textboxes = parse_paragraph(
                child, ctx.resolver, idx, in_table, table_pos, from_textbox)
            blocks.append(para)
            for tb in textboxes:
                blocks.extend(
                    walk_container(tb, ctx, in_table=in_table,
                                   table_pos=table_pos, from_textbox=True))
        elif tag == "tbl":
            blocks.append(_walk_table(child, ctx))
        elif tag == "sdt":
            content = child.find(w("sdtContent"))
            if content is not None:
                blocks.extend(walk_container(
                    content, ctx, in_table=in_table, table_pos=table_pos,
                    from_textbox=from_textbox))
        # anything else (sectPr, bookmarks, proofErr, ...) has no content
        # we care about, so it's just skipped
    return blocks


def _walk_table(tbl: etree._Element, ctx: Ctx) -> TableRef:
    idx = ctx.next_index()
    table_index = len(ctx.tables)
    table = Table(table_index=table_index, block_index=idx, rows=[])
    ctx.tables.append(table)  # add it now, before we recurse into its cells

    rows: list[Row] = []
    for r, tr in enumerate(tbl.findall(w("tr"))):
        cells: list[Cell] = []
        for c, tc in enumerate(tr.findall(w("tc"))):
            cell_blocks = walk_container(
                tc, ctx, in_table=True, table_pos=(table_index, r, c))
            cells.append(Cell(blocks=cell_blocks))
        rows.append(Row(cells=cells))
    table.rows = rows
    return TableRef(block_index=idx, table_index=table_index,
                    location=f"Table {table_index + 1}")


# --------------------------------------------------------------------------
# Paragraph parsing
# --------------------------------------------------------------------------
def parse_paragraph(p: etree._Element, resolver: StyleResolver,
                    block_index: int, in_table: bool,
                    table_pos: Optional[tuple],
                    from_textbox: bool) -> tuple[Paragraph, list]:
    props = resolver.resolve_para(p.find(w("pPr")))
    props.in_table = in_table

    sink = _RunSink(resolver, props.style_id)
    _walk_runs(p, sink)

    para = Paragraph(
        block_index=block_index,
        text="".join(sink.text),
        runs=merge_runs(sink.runs),
        props=props,
        fields=sink.fields.fields,
        in_table=in_table,
        from_textbox=from_textbox,
        table_pos=table_pos,
        location=_para_location(block_index, in_table, table_pos, from_textbox),
    )
    return para, sink.textboxes


_RECURSE_TAGS = {"hyperlink", "ins", "smartTag", "customXml"}


class _RunSink:
    """Collects everything found while walking one paragraph: its runs,
    text, fields, and any text boxes.

    This exists so the walking functions below don't need to pass around
    five or six separate arguments at every recursive call - they just
    pass this one object instead.
    """

    __slots__ = ("resolver", "style_id", "fields", "runs", "text", "textboxes")

    def __init__(self, resolver: StyleResolver, style_id: Optional[str]):
        self.resolver = resolver
        self.style_id = style_id
        self.fields = FieldCollector()
        self.runs: list[Run] = []
        self.text: list[str] = []
        self.textboxes: list[etree._Element] = []

    def emit(self, ch: str, font: ResolvedFont) -> None:
        self.runs.append(Run(text=ch, font=font))
        self.text.append(ch)
        self.fields.add_text(ch)


def _walk_runs(elem: etree._Element, sink: _RunSink) -> None:
    for child in elem:
        tag = local(child)
        if tag == "r":
            _walk_single_run(child, sink)
        elif tag == "fldSimple":
            instr = child.get(w("instr")) or ""
            before = len(sink.text)
            _walk_runs(child, sink)
            sink.fields.simple(instr, "".join(sink.text[before:]))
        elif tag == "sdt":
            content = child.find(w("sdtContent"))
            if content is not None:
                _walk_runs(content, sink)
        elif tag in _RECURSE_TAGS:
            _walk_runs(child, sink)
        elif tag == "del":
            continue  # tracked deletion: not part of the accepted document


def _walk_single_run(run: etree._Element, sink: _RunSink) -> None:
    font = sink.resolver.resolve_font(run.find(w("rPr")), sink.style_id)
    for rc in run:
        tag = local(rc)
        if tag == "t":
            sink.emit(rc.text or "", font)
        elif tag == "instrText":
            sink.fields.add_instr(rc.text or "")
        elif tag == "delInstrText":
            continue
        elif tag == "fldChar":
            ftype = rc.get(w("fldCharType"))
            if ftype == "begin":
                sink.fields.begin()
            elif ftype == "separate":
                sink.fields.separate()
            elif ftype == "end":
                sink.fields.end()
        elif tag == "tab":
            sink.emit("\t", font)
        elif tag in ("br", "cr"):
            sink.emit("\n", font)
        elif tag == "noBreakHyphen":
            sink.emit("-", font)
        elif tag in ("drawing", "pict", "object"):
            for txbx in rc.iter(w("txbxContent")):
                sink.textboxes.append(txbx)


def _para_location(idx: int, in_table: bool, table_pos: Optional[tuple],
                   from_textbox: bool) -> str:
    if in_table and table_pos is not None:
        t, r, c = table_pos
        return f"Table {t + 1}, row {r + 1}, cell {c + 1}"
    if from_textbox:
        return f"Text box (block {idx})"
    return f"Paragraph {idx}"
