"""Stable application error taxonomy used across adapter boundaries."""

from __future__ import annotations


class ApplicationError(Exception):
    code = "application_error"


class DomainError(ApplicationError):
    code = "domain_error"


class ValidationError(ApplicationError):
    code = "validation_error"


class InfrastructureError(ApplicationError):
    code = "infrastructure_error"


class UserCancelled(ApplicationError):
    code = "user_cancelled"


class OperationTimeout(ApplicationError):
    code = "timeout"


class SecurityViolation(ApplicationError):
    code = "security_violation"


class RevisionConflict(ApplicationError):
    code = "revision_conflict"

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"state revision conflict: expected {expected}, actual {actual}")
