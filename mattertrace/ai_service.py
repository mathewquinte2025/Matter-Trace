"""Replaceable AI matching interface (component 7) with a stub implementation.

No real AI provider is connected. A future provider must implement
`AIMatterService.suggest` and return data in OUTPUT FORMAT below. Whatever it
returns is treated as untrusted: `validate_ai_output` keeps only well-formed
suggestions for permitted matter IDs that cite real segments of the document.
Model free text is never stored or shown to reviewers.

OUTPUT FORMAT:
    {"candidates": [
        {"matter_id": "MT-1001", "confidence": 0.72,
         "evidence_segment_ids": [12, 13]}
    ]}
"""
from dataclasses import dataclass
from typing import Any, Protocol

from .errors import AIServiceError


class AIMatterService(Protocol):
    name: str
    version: str

    def suggest(self, segments: list[dict], matter_context: list[dict]) -> Any:
        """segments: [{segment_id, text}], matter_context: minimal permitted matter fields."""


class StubAIService:
    """Placeholder that returns a valid, empty answer ("no additional suggestions")."""
    name = "stub"
    version = "0.1"

    def suggest(self, segments, matter_context):
        return {"candidates": []}


def build_ai_service(name: str) -> AIMatterService | None:
    if name == "stub":
        return StubAIService()
    if name in ("none", "", None):
        return None
    raise ValueError(f"Unknown AI service '{name}'. This prototype only provides 'stub'.")


@dataclass
class AISuggestion:
    matter_id: str
    confidence: float
    segment_ids: list[int]


def validate_ai_output(raw: Any, permitted_matter_ids: set[str],
                       valid_segment_ids: set[int]) -> tuple[list[AISuggestion], list[str]]:
    """Return (valid suggestions, warnings). Raise AIServiceError if the shape is unusable."""
    if not isinstance(raw, dict) or not isinstance(raw.get("candidates"), list):
        raise AIServiceError("AI service returned malformed output (expected a 'candidates' list).")
    suggestions, warnings = [], []
    for item in raw["candidates"]:
        if not isinstance(item, dict):
            warnings.append("Ignored a malformed AI suggestion.")
            continue
        matter_id = item.get("matter_id")
        confidence = item.get("confidence")
        seg_ids = item.get("evidence_segment_ids")
        if not isinstance(matter_id, str) or matter_id not in permitted_matter_ids:
            warnings.append("Ignored an AI suggestion for an unknown or unauthorized matter.")
            continue
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            warnings.append(f"Ignored an AI suggestion for {matter_id} with an invalid confidence value.")
            continue
        if not isinstance(seg_ids, list):
            seg_ids = []
        traceable = [s for s in seg_ids if isinstance(s, int) and not isinstance(s, bool) and s in valid_segment_ids]
        if not traceable:
            warnings.append(f"Ignored an AI suggestion for {matter_id} with no traceable evidence.")
            continue
        suggestions.append(AISuggestion(matter_id, round(float(confidence), 2), traceable))
    return suggestions, warnings
