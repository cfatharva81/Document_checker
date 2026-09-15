"""Shared rule questions and prompts for retrieval-backed evaluation."""
from __future__ import annotations

RULE_QUESTIONS: dict[int, str] = {
	1: "Is the document title present on the first page and does it match the filename?",
	2: "Are the author name and author role mentioned in the document?",
	3: "Are the revision-history dates present, valid, ordered, and not in the future?",
	4: "Does the version number appear consistently in the title, first page, and revision history?",
	5: "Is a revision section present in the document?",
	6: "Does the document include signature blocks?",
	7: "Are dates present near the signature blocks?",
	8: "Is the document's basic font and spacing formatting consistent?",
	9: "Are there language errors that should be corrected in the document?",
	10: "Are the required sections present, including Objective or Purpose and Scope?",
	11: "Are page numbers present and sequential?",
	12: "Is the document readable based on sentence length and word complexity?",
	13: "Does the footer contain the document ID, page number, and confidentiality details?",
}


def rule_question(rule_id: int) -> str:
	try:
		return RULE_QUESTIONS[rule_id]
	except KeyError as exc:
		raise ValueError(f"unknown rule id: {rule_id}") from exc


def build_gemini_prompt(rule_id: int, context: str) -> str:
	"""Build a strict JSON classification prompt for one rule."""
	return f"""You are evaluating an SOP document against one compliance rule.

Rule {rule_id}: {rule_question(rule_id)}

Use only the supplied document evidence. Do not infer facts that are absent.
Return exactly one JSON object with this shape:
{{
  "passed": true,
  "evidence": "A concise, readable explanation grounded in the evidence.",
  "locations": ["The source locations used"]
}}

The value of "passed" must be a JSON boolean, never a string. Set it to
false when the evidence is missing, contradictory, or does not satisfy the
rule. Do not include markdown fences or additional keys.

Document evidence:
{context}
"""
