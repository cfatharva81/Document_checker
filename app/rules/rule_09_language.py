"""Rule 9 - Language errors via an injected LanguageTool checker.

The checker is fed one paragraph at a time -- never concatenated document
text, which would invent sentence boundaries and flood the report with false
capitalisation errors. Headings, table cells and short paragraphs are skipped.
Whitespace/quote/sentence-start rules are disabled, and a caller-supplied
ignore list suppresses acronyms and product names.

Three more sources of noise are filtered by default, on top of the caller's
own ignore list:

- **Doc-code-like tokens** ("DEV-YYYY-NNN", "SOP-QA-014") are template
  placeholders and identifiers, not English words, so LanguageTool's spell
  checker has nothing to check them against. Anything shaped like an
  identifier (uppercase segments joined by hyphens/underscores) is skipped.
- **Common QA/root-cause-analysis jargon** ("five-whys", "fishbone", ...)
  is real technical vocabulary that a general-purpose dictionary simply
  doesn't carry. A small default list covers the standard terms; callers
  can extend it with ignore_words for house-specific jargon.
- **British/American spelling variants** are a locale choice, not an
  error -- LanguageTool runs as en-US, so "authorises" is flagged only
  because it's the British form, not because it is misspelled. Any match
  whose own message says it is flagging a spelling variant is dropped.
"""
from __future__ import annotations

import re

from app.extractor import Doc
from .base import Rule, RuleConfig, Finding, heading_level


# The spec asks to disable whitespace, smart-quote and sentence-start-capital
# rules. Those intents map to several concrete LanguageTool ids depending on
# version, so we disable the whole family. This is the single source of truth,
# reused by the LanguageTool wrapper in app/deps.py.
DISABLED_RULE_IDS = {
    # whitespace noise
    "WHITESPACE_RULE",
    "CONSECUTIVE_SPACES",
    "SENTENCE_WHITESPACE",
    # smart quotes
    "EN_QUOTES",
    # capitalisation at (invented) sentence starts
    "UPPERCASE_SENTENCE_START",
}

# A doc code or template placeholder: "DEV-YYYY-NNN", "SOP-QA-014",
# "CAPA-2024-001". Not natural-language text, so a spelling flag on one of
# these is always a false positive.
_IDENTIFIER_RE = re.compile(r"^[A-Z]{2,}(?:[-_][A-Z0-9]{1,6}){1,4}$")

# Standard QA / root-cause-analysis terminology that general-purpose
# dictionaries don't carry. Extend per document via config.ignore_words
# rather than growing this list for house-specific jargon.
DEFAULT_IGNORE_TERMS = {
    "five-whys", "five whys", "5-whys", "fishbone", "ishikawa", "pareto",
    "kaizen", "gemba", "poka-yoke", "capa",
}

# LanguageTool flags this as a spelling "mistake" but is really just telling
# you the word is the other English variant (British vs. American) -- not
# a real error given the wording used elsewhere in these messages.
_SPELLING_VARIANT_RE = re.compile(
    r"\bis (?:British|American) English\b", re.IGNORECASE)

MAX_REPORTED = 50


class Rule09(Rule):
    id = 9
    name = "Language errors"
    severity = "warning"
    description = ("Grammar and spelling issues found by LanguageTool, "
                   "checked one paragraph at a time.")

    def evaluate(self, doc: Doc, config: RuleConfig) -> Finding:
        checker = config.language_checker
        if checker is None:
            return self.na(
                "Language checking is unavailable (no LanguageTool "
                "instance), so rule 9 was not evaluated.")

        ignore = ({w.lower() for w in (config.ignore_words or [])}
                  | DEFAULT_IGNORE_TERMS)
        min_words = config.min_words_for_language

        issues: list[str] = []
        locations: list[str] = []
        checked = 0

        for p in doc.body_paragraphs():
            if p.in_table:
                continue
            if heading_level(p) is not None:
                continue
            text = p.text.strip()
            if len(text.split()) < min_words:
                continue
            checked += 1
            for m in checker.check(text):
                if m.rule_id in DISABLED_RULE_IDS:
                    continue
                snippet = m.context.strip() or text
                if self._ignored(m, snippet, ignore):
                    continue
                issues.append(f"{m.message} — …{snippet}…")
                locations.append(p.location)
                if len(issues) >= MAX_REPORTED:
                    break
            if len(issues) >= MAX_REPORTED:
                break

        if checked == 0:
            return self.fail(
                "No body paragraphs long enough to language-check "
                f"(the floor is {min_words} words).")

        if issues:
            return self.fail(
                f"{len(issues)} language issue(s) found"
                + (" (capped)" if len(issues) >= MAX_REPORTED else "") + ".",
                evidence=issues, locations=locations, confidence="heuristic")
        return self.ok(
            f"No language issues found across {checked} paragraph(s).",
            confidence="heuristic")

    def _ignored(self, match, snippet: str, ignore: set) -> bool:
        # prefer the precisely flagged span; fall back to the context snippet
        raw_span = getattr(match, "matched_text", "") or snippet
        if _IDENTIFIER_RE.match(raw_span.strip()):
            return True
        if _SPELLING_VARIANT_RE.search(match.message):
            return True
        if not ignore:
            return False
        span = raw_span.lower()
        return any(term in span for term in ignore)


RULE = Rule09()
