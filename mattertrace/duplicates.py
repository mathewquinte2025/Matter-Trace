"""Duplicate / conflict checker (component 8).

Flags are warnings for a human. Nothing here deletes, merges, or replaces a document.
- exact_duplicate:   identical SHA-256 checksum (byte-identical file)
- possible_conflict: same reference number (invoice/account/...) but different
                     amount or date of service
- near_duplicate:    same reference number, or highly overlapping text
                     (possibly a revised or superseded version)
"""
import re
from dataclasses import dataclass

NEAR_DUPLICATE_THRESHOLD = 0.70  # word-trigram Jaccard overlap

REF_PATTERN = re.compile(
    r"\b(?:invoice|account|acct|statement|bill|record|report)\s*(?:no\.?|number|#)\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{3,})",
    re.IGNORECASE,
)
AMOUNT_PATTERN = re.compile(
    r"\b(?:total(?:\s+charges)?|amount\s+due|balance\s+due)\s*[:\-]?\s*\$\s?([\d,]+\.\d{2})",
    re.IGNORECASE,
)
DOS_PATTERN = re.compile(r"\bdate\s+of\s+service\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)


@dataclass
class FlagResult:
    compared_document_id: str
    flag_type: str
    similarity: float
    evidence: list[str]


def key_fields(text: str) -> dict[str, set[str]]:
    return {
        "reference": {m.upper() for m in REF_PATTERN.findall(text)},
        "amount": {m.replace(",", "") for m in AMOUNT_PATTERN.findall(text)},
        "date_of_service": set(DOS_PATTERN.findall(text)),
    }


def _shingles(text: str) -> set[tuple]:
    words = re.findall(r"\w+", text.lower())
    if len(words) < 3:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + 3]) for i in range(len(words) - 2)}


def text_similarity(a: str, b: str) -> float:
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def compare(new_doc: dict, new_text: str, other_doc: dict, other_text: str) -> FlagResult | None:
    """new_doc / other_doc need: document_id, filename, checksum_sha256."""
    other_label = f"{other_doc['document_id']} ({other_doc['filename']})"
    if new_doc["checksum_sha256"] == other_doc["checksum_sha256"]:
        return FlagResult(other_doc["document_id"], "exact_duplicate", 1.0, [
            f"Byte-identical to {other_label}: same SHA-256 checksum.",
        ])

    similarity = round(text_similarity(new_text, other_text), 2)
    a, b = key_fields(new_text), key_fields(other_text)
    shared_refs = a["reference"] & b["reference"]
    if shared_refs:
        refs = ", ".join(sorted(shared_refs))
        differences = []
        if a["amount"] and b["amount"] and a["amount"] != b["amount"]:
            differences.append(
                f"amounts differ: this document ${', $'.join(sorted(a['amount']))} vs "
                f"${', $'.join(sorted(b['amount']))} in {other_label}"
            )
        if a["date_of_service"] and b["date_of_service"] and a["date_of_service"] != b["date_of_service"]:
            differences.append(
                f"dates of service differ: {', '.join(sorted(a['date_of_service']))} vs "
                f"{', '.join(sorted(b['date_of_service']))}"
            )
        if differences:
            return FlagResult(other_doc["document_id"], "possible_conflict", similarity, [
                f"Same reference number ({refs}) as {other_label}, but " + "; ".join(differences) + ".",
                f"Text overlap: {similarity:.0%}.",
            ])
        return FlagResult(other_doc["document_id"], "near_duplicate", similarity, [
            f"Same reference number ({refs}) as {other_label}.",
            f"Text overlap: {similarity:.0%}. May be a copy or another version.",
        ])

    if similarity >= NEAR_DUPLICATE_THRESHOLD:
        return FlagResult(other_doc["document_id"], "near_duplicate", similarity, [
            f"Text overlaps {similarity:.0%} with {other_label}; it may be a revised or superseded version.",
        ])
    return None
