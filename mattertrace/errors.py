class AuthorizationError(Exception):
    """The authenticated user is not allowed to perform this action."""


class ValidationError(Exception):
    """The request is invalid (bad input or a disallowed status transition)."""


class ExtractionError(Exception):
    """Text could not be extracted from a stored file."""


class AIServiceError(Exception):
    """The AI service was unavailable or returned unusable output."""
