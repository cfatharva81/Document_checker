"""Turns a .docx file into a plain Doc model that the rules can read.

Nothing outside this package should ever import python-docx or lxml
directly - rules only ever see the Doc model.

The files in this package build on each other, from the ground up, so that
all the messy OOXML detail stays down in the lower files and never leaks
into the model the rules actually see:

    xmlutil   namespace, tag and unit helpers      (no deps)
    model     the dataclasses the rules read       (no deps)
    fields    PAGE/NUMPAGES and other field codes  -> model
    headings  declared + inferred heading levels   -> model
    styles    style and theme inheritance          -> xmlutil, headings, model
    walker    flow-ordered document walk           -> fields, styles, model
    sections  headers/footers and inheritance      -> walker, model
    build     build_doc() orchestration            -> everything above
"""
from .build import build_doc
from .model import (
    Block,
    Cell,
    CoreProps,
    Doc,
    Field,
    HeaderFooter,
    HeadingEntry,
    Paragraph,
    ParagraphProps,
    ResolvedFont,
    Row,
    Run,
    Section,
    StyleIndex,
    StyleInfo,
    Table,
    TableRef,
)

__all__ = [
    "build_doc",
    "Block",
    "Cell",
    "CoreProps",
    "Doc",
    "Field",
    "HeaderFooter",
    "HeadingEntry",
    "Paragraph",
    "ParagraphProps",
    "ResolvedFont",
    "Row",
    "Run",
    "Section",
    "StyleIndex",
    "StyleInfo",
    "Table",
    "TableRef",
]
