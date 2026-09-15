"""Rule 10 - Required sections present."""
from __future__ import annotations

from app.extractor import Doc
from .base import (
    Rule,
    RuleConfig,
    Finding,
    iter_headings,
    normalized_heading_text,
    normalize_key,
)


class Rule10(Rule):
    id = 10
    name = "Required sections"
    severity = "error"
    description = ("Document sections must use heading formatting; an "
                   "optional required-section list can check specific names.")

    def evaluate(self, doc: Doc, config: RuleConfig) -> Finding:
        headings = list(iter_headings(doc))
        evidence = [f"headings: {[h.text for h in headings]}"]
        required = [r for r in (config.required_sections or []) if r.strip()]
        if not required:
            if not headings:
                return self.fail(
                    "No properly formatted sections were found. Use heading "
                    "styles or consistent heading formatting for section "
                    "titles.", evidence=evidence)
            return self.ok(
                f"Found {len(headings)} properly formatted section(s).",
                evidence=evidence,
                locations=[h.location for h in headings],
                confidence="heuristic")

        heading_keys = {normalized_heading_text(h.text): h for h in headings}
        heading_norm = [(normalized_heading_text(h.text), h) for h in headings]

        present: list[str] = []
        missing: list[str] = []
        locations: list[str] = []

        for req in required:
            rkey = normalize_key(req)
            match = None
            if rkey in heading_keys:
                match = heading_keys[rkey]
            else:
                for hkey, h in heading_norm:
                    if hkey.startswith(rkey):
                        match = h
                        break
            if match is not None:
                present.append(req)
                locations.append(match.location)
            else:
                missing.append(req)

        if missing:
            return self.fail(
                "Missing required section(s): " + ", ".join(missing) + ".",
                evidence=evidence + [f"present: {present}"],
                locations=locations, confidence="heuristic")
        return self.ok(
            "All required sections are present: " + ", ".join(present) + ".",
            locations=locations, confidence="heuristic")


RULE = Rule10()
