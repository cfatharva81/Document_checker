"""Field codes: the two ways Word stores things like page numbers.

Word can write a field as a "complex" field (w:fldChar, split across several
runs) or a "simple" one (w:fldSimple, all in one place). Either way it also
caches the last value it displayed. FieldCollector puts the pieces back
together as the paragraph walker passes them along. Rule 11 reads the result.
"""
from __future__ import annotations

from .model import Field


def classify(instruction: str) -> str:
    """The field's type: the first word of the instruction, upper-cased
    (e.g. PAGE, NUMPAGES, REF, DATE)."""
    if not instruction:
        return ""
    tok = instruction.strip().lstrip('"').split()
    return tok[0].upper() if tok else ""


class FieldCollector:
    """Accumulates fields as the paragraph walker streams run tokens."""

    def __init__(self) -> None:
        self.fields: list[Field] = []
        # stack of fields we're still in the middle of reading.
        # each entry is [instr_parts, result_parts, phase], where phase is
        # either "instr" (still reading the instruction) or "result"
        # (now reading the cached value)
        self._stack: list[list] = []

    # -- complex field events -----------------------------------------
    def begin(self) -> None:
        self._stack.append([[], [], "instr"])

    def separate(self) -> None:
        if self._stack:
            self._stack[-1][2] = "result"

    def add_instr(self, text: str) -> None:
        if self._stack and self._stack[-1][2] == "instr":
            self._stack[-1][0].append(text)

    def add_text(self, text: str) -> None:
        """Regular run text; captured as result if a field is open."""
        if self._stack and self._stack[-1][2] == "result":
            self._stack[-1][1].append(text)

    def end(self) -> None:
        if not self._stack:
            return
        instr_parts, result_parts, _ = self._stack.pop()
        instruction = "".join(instr_parts).strip()
        result = "".join(result_parts).strip()
        self.fields.append(Field(
            kind=classify(instruction),
            instruction=instruction,
            result=result,
            simple=False,
        ))

    # -- simple field --------------------------------------------------
    def simple(self, instruction: str, result: str) -> None:
        instruction = (instruction or "").strip()
        self.fields.append(Field(
            kind=classify(instruction),
            instruction=instruction,
            result=(result or "").strip(),
            simple=True,
        ))

