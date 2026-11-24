"""Deterministic rule-based matter matcher (components 6 and 7, baseline).

Only matters the user may access are passed in (candidate retrieval is
matter-scoped by the caller). Each signal found adds a fixed weight; every
signal records where it was found so a reviewer can trace it (FR-03, NFR-03).
"""
import re
from dataclasses import dataclass, field
from datetime import datetime

from .extraction import location_label

MATCHER_NAME = "rules"
MATCHER_VERSION = "1.0"

# Signal weights. A score is the capped sum of the weights of signals found.
WEIGHTS = {
    "MATTER_NUMBER": 0.50,
    "CLAIM_NUMBER": 0.50,
    "CLIENT_NAME": 0.35,
    "CLIENT_DOB": 0.25,
    "INCIDENT_DATE": 0.10,
}

SIGNAL_LABELS = {
    "MATTER_NUMBER": "Matter number",
    "CLAIM_NUMBER": "Claim number",
    "CLIENT_NAME": "Client name",
    "CLIENT_DOB": "Client date of birth",
    "INCIDENT_DATE": "Incident date",
}

MAX_CANDIDATES = 3


@dataclass
class CandidateResult:
    matter_id: str
    score: float
    reasons: list[dict] = field(default_factory=list)


def uncertainty_label(score: float, threshold: float) -> str:
    if score >= 0.85:
        return "High"
    if score >= threshold:
        return "Medium"
    return "Low"


def _identifier_pattern(identifier: str) -> str:
    """'CF-88213-A' matches 'CF-88213-A', 'CF 88213 A', 'cf88213a'."""
    parts = [re.escape(p) for p in re.split(r"[^A-Za-z0-9]+", identifier) if p]
    return r"(?<![A-Za-z0-9])" + r"[-\s]?".join(parts) + r"(?![A-Za-z0-9])"


def _name_patterns(full_name: str) -> list[str]:
    parts = full_name.split()
    first, last = re.escape(parts[0]), re.escape(parts[-1])
    return [rf"\b{first}\s+{last}\b", rf"\b{last},\s*{first}\b"]


def _date_patterns(mmddyyyy: str) -> list[str]:
    d = datetime.strptime(mmddyyyy, "%m/%d/%Y")
    m, day, y = d.month, d.day, d.year
    return [
        rf"(?<!\d)0?{m}/0?{day}/{y}(?!\d)",
        rf"(?<!\d){y}-{m:02d}-{day:02d}(?!\d)",
        rf"\b{d.strftime('%B')}\s+{day},?\s+{y}\b",
    ]


def matter_patterns(matter) -> dict[str, list[str]]:
    patterns = {"MATTER_NUMBER": [_identifier_pattern(matter["matter_id"])],
                "CLIENT_NAME": _name_patterns(matter["client_name"])}
    if matter["claim_number"]:
        patterns["CLAIM_NUMBER"] = [_identifier_pattern(matter["claim_number"])]
    if matter["client_dob"]:
        patterns["CLIENT_DOB"] = _date_patterns(matter["client_dob"])
    if matter["incident_date"]:
        patterns["INCIDENT_DATE"] = _date_patterns(matter["incident_date"])
    return patterns


def _excerpt(text: str, start: int, end: int, width: int = 50) -> str:
    snippet = text[max(0, start - width):min(len(text), end + width)]
    snippet = " ".join(snippet.split())
    return ("..." if start > width else "") + snippet + ("..." if end + width < len(text) else "")


def _find_first(patterns: list[str], segments: list[dict], metadata: dict[str, str]):
    """Return evidence for the first occurrence: in document text first, then metadata."""
    for seg in segments:
        for pat in patterns:
            m = re.search(pat, seg["text"], re.IGNORECASE)
            if m:
                return {
                    "source": "document",
                    "segment_id": seg["segment_id"],
                    "location": location_label(seg["page_number"], seg["segment_index"]),
                    "matched_text": m.group(0),
                    "excerpt": _excerpt(seg["text"], m.start(), m.end()),
                }
    for field_name, value in metadata.items():
        for pat in patterns:
            m = re.search(pat, value or "", re.IGNORECASE)
            if m:
                return {
                    "source": "metadata",
                    "segment_id": None,
                    "location": field_name,
                    "matched_text": m.group(0),
                    "excerpt": value,
                }
    return None


def match_document(segments: list[dict], metadata: dict[str, str], matters) -> list[CandidateResult]:
    """Score each permitted matter; return up to MAX_CANDIDATES with score > 0, best first."""
    results = []
    for matter in matters:
        reasons = []
        for code, patterns in matter_patterns(matter).items():
            evidence = _find_first(patterns, segments, metadata)
            if evidence:
                reasons.append({
                    "code": code,
                    "label": f"{SIGNAL_LABELS[code]} '{evidence['matched_text']}' found in {evidence['location']}",
                    "weight": WEIGHTS[code],
                    **evidence,
                })
        if reasons:
            score = round(min(1.0, sum(r["weight"] for r in reasons)), 2)
            results.append(CandidateResult(matter["matter_id"], score, reasons))
    results.sort(key=lambda c: (-c.score, c.matter_id))
    return results[:MAX_CANDIDATES]
