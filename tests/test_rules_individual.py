"""Targeted per-rule assertions: na-states, evidence, and edge behaviour."""
from __future__ import annotations

import pytest

from app.engine import get_rule
from app.rules import RuleConfig
from tests import make_fixtures as mf
from tests.conftest import StubChecker


def _run(rule_id, doc, config):
    return get_rule(rule_id).evaluate(doc, config)


# ---- rule 1 -------------------------------------------------------------
def test_rule1_na_without_title_or_heading(extract_doc, config):
    d = mf.Document()
    d.add_paragraph("just some plain text with no heading")
    f = _run(1, extract_doc(d, filename="anything.docx"), config)
    assert f.passed is False
    assert "states no title" in f.message


def test_rule1_pass_on_match(extract_doc, config):
    d = mf.Document()
    mf.set_core(d, title="Onboarding Guide")
    d.add_heading("Onboarding Guide", level=1)
    f = _run(1, extract_doc(d, filename="Onboarding-Guide-v2.docx"), config)
    assert f.passed is True


def test_rule1_uses_cover_title_before_introduction(extract_doc, config):
    d = mf.Document()
    d.add_paragraph("Deployment Report")
    d.add_heading("Introduction", level=1)
    f = _run(1, extract_doc(
        d, filename="Deployment Report_v0 - filled (1) (1).docx"), config)
    assert f.passed is True, f.message
    assert any("first-page title" in e for e in f.evidence)


def _rule1(extract_doc, config, filename, title="Onboarding Guide"):
    d = mf.Document()
    mf.set_core(d, title=title)
    d.add_heading(title, level=1)
    return _run(1, extract_doc(d, filename=filename), config)


@pytest.mark.parametrize("filename", [
    "Onboarding Guide final.docx",      # bare keyword, no version digits
    "Onboarding Guide copy.docx",
    "Onboarding Guide - Copy.docx",     # Windows duplicate
    "Onboarding Guide draft.docx",
    "Onboarding Guide (1).docx",        # browser duplicate download
    "Onboarding Guied.docx",            # transposition typo
    "Guide for Onboarding.docx",        # reordered tokens
])
def test_rule1_fuzzy_accepts_near_misses(extract_doc, config, filename):
    f = _rule1(extract_doc, config, filename)
    assert f.passed is True, f.message
    assert f.confidence == "heuristic"


@pytest.mark.parametrize("filename", [
    "Completely Other Name.docx",
    "Invoice Template.docx",
    "Safety Manual.docx",
])
def test_rule1_fuzzy_still_rejects_unrelated_names(extract_doc, config,
                                                   filename):
    assert _rule1(extract_doc, config, filename).passed is False


def test_rule1_fuzzy_rejects_document_number_mismatch(extract_doc, config):
    """Near-identical strings that disagree on a number are different docs."""
    f = _rule1(extract_doc, config, "SOP-002 Cleaning Procedure.docx",
               title="SOP-001 Cleaning Procedure")
    assert f.passed is False, f.message


def test_rule1_threshold_of_one_restores_exact_matching(extract_doc):
    # a typo is the case only the fuzzy pass can rescue -- suffix noise is
    # already handled deterministically in normalisation
    cfg = RuleConfig(title_match_threshold=1.0)
    assert _rule1(extract_doc, cfg, "Onboarding Guied.docx").passed is False
    assert _rule1(extract_doc, cfg, "Onboarding Guide (1).docx").passed is True


def test_rule1_suffix_noise_is_stripped_not_merely_tolerated(extract_doc,
                                                             config):
    """final / copy / (n) should match exactly, independent of title length,
    so a short title is not penalised by a fixed-length suffix."""
    for name in ["Guide final.docx", "Guide copy.docx", "Guide (1).docx"]:
        f = _rule1(extract_doc, config, name, title="Guide")
        assert f.passed is True, f.message
        assert not any("similarity" in e for e in f.evidence), f.evidence


def test_rule1_reports_the_score_as_evidence(extract_doc, config):
    f = _rule1(extract_doc, config, "Invoice Template.docx")
    assert any("similarity" in e for e in f.evidence), f.evidence


# ---- rule 3 -------------------------------------------------------------
def test_rule3_fails_without_revision_table(extract_doc, config):
    f = _run(3, extract_doc(mf.golden_sop(break_revision_section=True)), config)
    assert f.passed is False
    assert "no revision dates" in f.message


def test_rule3_reports_future_and_unordered(extract_doc, config):
    f = _run(3, extract_doc(mf.golden_sop(break_rev_dates=True)), config)
    assert f.passed is False
    joined = f.message.lower()
    assert "future" in joined or "order" in joined


# ---- rule 4 -------------------------------------------------------------
def test_rule4_fails_when_no_version_is_stated_anywhere(extract_doc, config):
    f = _run(4, extract_doc(mf.golden_sop(break_version=True)), config)
    assert f.passed is False
    assert "No version number" in f.message
    # a bare "not found" is not actionable: say where it looked
    assert any("Searched" in e for e in f.evidence)


def test_rule4_reports_where_each_version_is_stated(extract_doc, config):
    f = _run(4, extract_doc(mf.golden_sop()), config)
    assert f.passed is True
    assert "1.2" in f.message
    joined = " ".join(f.evidence)
    assert "Header" in joined and "Paragraph" in joined


def test_rule4_no_longer_judges_consistency(extract_doc, config):
    """Deliberate: rule 4 asks whether a version exists, not whether every
    stated version agrees. A header and body that disagree still pass."""
    document = mf.golden_sop()
    document.sections[0].header.paragraphs[0].text = "Version 1.1"
    f = _run(4, extract_doc(document), config)
    assert f.passed is True
    assert "1.1" in f.message and "1.2" in f.message


# ---- rule 5 -------------------------------------------------------------
def test_rule5_fail_without_section(extract_doc, config):
    f = _run(5, extract_doc(mf.golden_sop(break_revision_section=True)), config)
    assert f.passed is False


# ---- rule 6 -------------------------------------------------------------
def test_rule6_evidence_quotes_the_line_and_names_its_section(extract_doc,
                                                              config):
    f = _run(6, extract_doc(mf.golden_sop()), config)
    assert f.passed is True
    prepared = next(e for e in f.evidence if "Prepared by" in e)
    assert "Paragraph" in prepared           # where it is
    assert "Jane Smith" in prepared          # what it says
    assert "under" in prepared               # which section it sits under


def test_rule6_says_what_it_searched_for_when_it_finds_nothing(extract_doc,
                                                               config):
    f = _run(6, extract_doc(mf.golden_sop(break_signature=True)), config)
    assert f.passed is False
    joined = " ".join(f.evidence)
    assert "Searched" in joined and "Looked for" in joined


# ---- rule 7 -------------------------------------------------------------
def test_rule7_fails_without_signatures(extract_doc, config):
    f = _run(7, extract_doc(mf.golden_sop(break_signature=True)), config)
    assert f.passed is False


def test_rule7_checks_signature_table_rows(extract_doc, config):
    d = mf.Document()
    d.add_heading("Signature Verification Log", level=1)
    table = d.add_table(rows=2, cols=3)
    for cell, text in zip(table.rows[0].cells,
                          ["Name", "Signature", "Date"]):
        cell.text = text
    for cell, text in zip(table.rows[1].cells,
                          ["Jane Smith", "Signed", "01/02/2024"]):
        cell.text = text
    f = _run(7, extract_doc(d, filename="deployment.docx"), config)
    assert f.passed is True, f.message
    assert "Table 1, row 2" in f.evidence[0]


def test_rule7_ignores_revision_table_rows(extract_doc, config):
    d = mf.Document()
    d.add_heading("Revision History", level=1)
    table = d.add_table(rows=2, cols=4)
    for cell, text in zip(table.rows[0].cells,
                          ["Revision", "Date", "Name", "Description"]):
        cell.text = text
    for cell, text in zip(table.rows[1].cells,
                          ["1.0", "01/02/2024", "Jane Smith", "Update"]):
        cell.text = text
    f = _run(7, extract_doc(d, filename="deployment.docx"), config)
    assert f.passed is False
    assert "No signature blocks found" in f.message


def test_rule7_does_not_treat_signature_heading_as_a_block(extract_doc,
                                                            config):
    d = mf.Document()
    d.add_heading("Signature Verification Log", level=1)
    f = _run(7, extract_doc(d, filename="deployment.docx"), config)
    assert f.passed is False
    assert "No signature blocks found" in f.message
    assert not any("Signature Verification Log" in e for e in f.evidence)


def test_rule7_evidence_says_where_the_date_came_from(extract_doc, config):
    f = _run(7, extract_doc(mf.golden_sop()), config)
    assert f.passed is True
    assert all("01/02/2024" in e for e in f.evidence)
    assert all("on the signature line itself" in e for e in f.evidence)


def test_rule7_undated_evidence_names_the_span_searched(extract_doc, config):
    f = _run(7, extract_doc(mf.golden_sop(break_sig_dates=True)), config)
    assert f.passed is False
    assert all("no date on the line" in e for e in f.evidence)
    assert all("block(s) either side" in e for e in f.evidence)


# ---- rule 8 -------------------------------------------------------------
def test_rule8_locations_point_at_offending_paragraph(extract_doc, config):
    f = _run(8, extract_doc(mf.golden_sop(break_fonts=True)), config)
    assert f.passed is False
    assert f.locations
    assert any("Times New Roman" in e for e in f.evidence)


def test_rule8_evidence_quotes_the_paragraph_and_names_the_baseline(
        extract_doc, config):
    f = _run(8, extract_doc(mf.golden_sop(break_fonts=True)), config)
    offender = next(e for e in f.evidence if "Times New Roman" in e)
    assert "different typeface entirely" in offender   # the text itself
    assert "instead of Calibri" in offender            # what it should be
    # the baseline is stated whether or not anything deviated
    assert any("body style" in e for e in f.evidence)
    assert any("body style" in e for e in _run(
        8, extract_doc(mf.golden_sop()), config).evidence)


# ---- rule 9 -------------------------------------------------------------
def test_rule9_flags_the_seeded_misspellings(extract_doc, config):
    f = _run(9, extract_doc(mf.golden_sop(break_language=True)), config)
    assert f.passed is False
    joined = " ".join(f.evidence)
    for typo in ("shold", "recieve", "teh"):
        assert typo in joined, joined
    assert f.locations


def test_rule9_clean_document_passes_the_same_checker(extract_doc, config):
    """The fail fixture is what makes the difference, not the stub: the very
    same checker reports nothing against the golden SOP."""
    f = _run(9, extract_doc(mf.golden_sop()), config)
    assert f.passed is True, f.evidence


# ---- rule 10 ------------------------------------------------------------
def test_rule10_checks_headings_when_no_required_list(extract_doc):
    cfg = RuleConfig(required_sections=[], language_checker=StubChecker())
    f = _run(10, extract_doc(mf.golden_sop()), cfg)
    assert f.passed is True
    assert "properly formatted" in f.message


def test_rule10_uses_headings_by_default(extract_doc):
    """No section list is needed when the document has formatted headings."""
    cfg = RuleConfig(language_checker=StubChecker())
    assert cfg.required_sections == []
    assert _run(10, extract_doc(mf.golden_sop()), cfg).passed is True


def test_rule10_lists_missing(extract_doc, config):
    f = _run(10, extract_doc(mf.golden_sop(break_required=True)), config)
    assert f.passed is False
    assert "References" in f.message


# ---- rule 11 ------------------------------------------------------------
def test_rule11_fails_without_footers(extract_doc, config):
    f = _run(11, extract_doc(mf.doc_no_headers_footers()), config)
    assert f.passed is False
    assert "limitation" in f.message.lower() or "does not verify" in f.message


def test_rule11_flags_hardcoded_number(extract_doc, config):
    f = _run(11, extract_doc(mf.golden_sop(break_page_field=True)), config)
    assert f.passed is False
    assert "hardcoded" in f.message.lower()


def test_rule11_passes_with_field_and_notes_numpages(extract_doc, config):
    f = _run(11, extract_doc(mf.golden_sop()), config)
    assert f.passed is True
    assert "NUMPAGES" in f.message


# ---- rule 12 ------------------------------------------------------------
def test_rule12_na_on_thin_document(extract_doc, config):
    d = mf.Document()
    mf.body_para(d, "Short and sweet body text here today.")
    f = _run(12, extract_doc(d), config)
    assert f.passed is False
    assert "word floor" in f.message


# ---- rule 13 ------------------------------------------------------------
def test_rule13_reports_missing_details(extract_doc, config):
    f = _run(13, extract_doc(mf.golden_sop(break_footer_details=True)), config)
    assert f.passed is False
    assert "document ID" in f.message or "confidentiality" in f.message
