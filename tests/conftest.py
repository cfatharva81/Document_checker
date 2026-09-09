"""Shared fixtures for rule and API tests."""
from __future__ import annotations

import re

import pytest

from app.extractor import build_doc
from app.rules import RuleConfig
from app.rules.base import COMMON_REQUIRED_SECTIONS
from app.rules.base import LanguageIssue
from tests import make_fixtures as mf


class StubChecker:
    """Stand-in for the LanguageTool wrapper so the suite needs no JVM.

    Returns the same canned issues for every paragraph, which is all most
    rule 9 tests need. It cannot tell a clean document from a defective one,
    though -- see :class:`TypoChecker` for the cases that turn on that.
    """

    def __init__(self, issues=None):
        self._issues = list(issues or [])

    def check(self, text: str):
        return list(self._issues)


# Misspellings the rule 9 fail fixture seeds, and the corrections real
# LanguageTool would offer for them.
TYPOS = {
    "teh": "the",
    "recieve": "receive",
    "shold": "should",
    "occured": "occurred",
    "seperate": "separate",
}

_WORD = re.compile(r"[A-Za-z']+")


class TypoChecker:
    """A LanguageTool stand-in that actually reads the text.

    Real LanguageTool needs a JVM and a ~200 MB download, which the suite
    must not require. But a checker that answers the same way whatever it is
    given cannot prove that rule 9 responds to the document -- it would
    report the golden SOP and the fail fixture identically. This one flags a
    fixed word list wherever it appears, so 'the fixture is what failed, not
    the stub' is a claim the tests can actually make.
    """

    def __init__(self, typos=None):
        self._typos = dict(TYPOS if typos is None else typos)

    def check(self, text: str):
        issues = []
        for m in _WORD.finditer(text or ""):
            word = m.group(0)
            correction = self._typos.get(word.lower())
            if correction is None:
                continue
            issues.append(LanguageIssue(
                message=f"Possible spelling mistake: {word!r}",
                context=text, offset=m.start(), length=len(word),
                rule_id="MORFOLOGIK_RULE_EN_US",
                matched_text=word, replacements=[correction],
            ))
        return issues


@pytest.fixture
def stub_checker():
    return StubChecker()


@pytest.fixture
def typo_checker():
    return TypoChecker()


@pytest.fixture
def language_issue():
    return LanguageIssue(
        message="Possible spelling mistake found",
        context="teh team",
        offset=0, length=3,
        rule_id="MORFOLOGIK_RULE_EN_US",
        replacements=["the"],
    )


@pytest.fixture
def config(typo_checker):
    # The shared config uses the reading checker, not the canned one: it
    # returns nothing for clean text, so every other rule's tests are
    # unaffected, and rule 9 can have a fail fixture like the other twelve.
    # Rule 10 has no built-in section list, so the suite states one.
    return RuleConfig(language_checker=typo_checker,
                      required_sections=list(COMMON_REQUIRED_SECTIONS))


@pytest.fixture
def extract_doc():
    def _extract(document, filename="Quality Control Procedure.docx"):
        return build_doc(mf.to_bytes(document), filename)
    return _extract
