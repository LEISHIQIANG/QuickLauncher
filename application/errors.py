"""Stable application error taxonomy used across adapter boundaries."""

from __future__ import annotations


class ApplicationError(Exception):
    code = "application_error"


class DomainError(ApplicationError):
    code = "domain_error"


class ValidationError(ApplicationError, ValueError):
    """Raised when data fails schema or business-rule validation."""

    code = "validation_error"


class InfrastructureError(ApplicationError, RuntimeError):
    """Raised when an infrastructure adapter encounters a fatal error."""

    code = "infrastructure_error"


class UserCancelled(ApplicationError):
    code = "user_cancelled"


class OperationTimeout(ApplicationError, TimeoutError):
    """Raised when an operation exceeds its allotted time budget."""

    code = "timeout"


class SecurityViolation(ApplicationError):
    code = "security_violation"


class RevisionConflict(ApplicationError):
    code = "revision_conflict"

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"state revision conflict: expected {expected}, actual {actual}")
