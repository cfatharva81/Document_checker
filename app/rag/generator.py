"""Optional Gemini judge for retrieval-backed rule answers."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .prompts import build_gemini_prompt


@dataclass(frozen=True)
class GeminiDecision:
	passed: bool
	evidence: str
	locations: list[str]


class GeminiGenerator:
	"""Ask Gemini for one strict binary decision from retrieved evidence."""

	def __init__(self, client: Any = None,
				 model: str = "gemini-3.5-flash-lite") -> None:
		self.model = model
		if client is not None:
			self.client = client
			return
		try:
			from google import genai
		except ImportError as exc:
			raise RuntimeError(
				"Gemini mode requires google-genai. "
				"Install it with: pip install google-genai"
			) from exc
		try:
			from dotenv import load_dotenv
		except ImportError as exc:
			raise RuntimeError(
				"Loading .env requires python-dotenv. "
				"Install it with: pip install -r requirements.txt"
			) from exc
		load_dotenv()
		api_key = os.getenv("GEMINI_API_KEY")
		if not api_key:
			raise RuntimeError("GEMINI_API_KEY is required for Gemini mode")
		self.client = genai.Client(api_key=api_key)

	def evaluate(self, rule_id: int, context: str) -> GeminiDecision:
		response = self.client.models.generate_content(
			model=self.model,
			contents=build_gemini_prompt(rule_id, context),
			config={"response_mime_type": "application/json"},
		)
		text = getattr(response, "text", None)
		if not isinstance(text, str) or not text.strip():
			raise ValueError("Gemini returned an empty response")
		return self._parse(text)

	@staticmethod
	def _parse(text: str) -> GeminiDecision:
		cleaned = text.strip()
		if cleaned.startswith("```"):
			cleaned = cleaned.split("\n", 1)[1]
			cleaned = cleaned.rsplit("```", 1)[0].strip()
		try:
			payload = json.loads(cleaned)
		except json.JSONDecodeError as exc:
			raise ValueError("Gemini response was not valid JSON") from exc
		if not isinstance(payload, dict) or not isinstance(payload.get("passed"), bool):
			raise ValueError("Gemini response must contain a boolean 'passed'")
		evidence = payload.get("evidence")
		if not isinstance(evidence, str) or not evidence.strip():
			raise ValueError("Gemini response must contain text 'evidence'")
		locations = payload.get("locations", [])
		if not isinstance(locations, list) or not all(
			isinstance(location, str) for location in locations
		):
			raise ValueError("Gemini response 'locations' must be a string list")
		return GeminiDecision(
			passed=payload["passed"],
			evidence=evidence.strip(),
			locations=locations,
		)
