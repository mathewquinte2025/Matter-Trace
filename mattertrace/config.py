"""Prototype settings. Values can be overridden with environment variables."""
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".txt": "txt"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

SOURCE_TYPES = [
    "Client upload",
    "Email",
    "Mail",
    "Provider portal",
    "Insurer",
    "Court",
    "Other",
]

# Document / matter-association statuses (Assignment 2, section 7.6).
# "Candidate Ready" is the "Candidate" status named in NFR-04.
RECEIVED = "Received"
PROCESSING = "Processing"
CANDIDATE_READY = "Candidate Ready"
NEEDS_REVIEW = "Needs Review"
CONFIRMED = "Confirmed"
CORRECTED = "Corrected"
REJECTED = "Rejected"
ESCALATED = "Escalated"
PROCESSING_FAILED = "Processing Failed"

# Statuses for individual candidate / duplicate-flag records.
CANDIDATE = "Candidate"
SUPERSEDED = "Superseded"  # replaced by a later retry; kept for history


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    confidence_threshold: float = 0.60
    # If the second-best matter scores within this margin of the best,
    # the result is treated as ambiguous and sent to mandatory review.
    ambiguity_margin: float = 0.15
    ai_service: str = "stub"  # "stub" or "none"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mattertrace.db"

    @property
    def originals_dir(self) -> Path:
        return self.data_dir / "originals"


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("MATTERTRACE_DATA_DIR", PROJECT_ROOT / "data")),
        confidence_threshold=float(os.environ.get("MATTERTRACE_CONFIDENCE_THRESHOLD", "0.60")),
        ai_service=os.environ.get("MATTERTRACE_AI_SERVICE", "stub"),
    )
