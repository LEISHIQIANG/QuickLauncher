"""Error types for command preprocessing."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationError:
    """Validation error with actionable guidance."""

    field: str
    error_code: str
    message: str
    severity: str = "error"
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "error_code": self.error_code,
            "message": self.message,
            "severity": self.severity,
            "suggestion": self.suggestion,
        }


@dataclass
class SecurityWarning:
    """Security issue with mitigation guidance."""

    issue_type: str
    severity: str
    description: str
    mitigation: str = ""
    allow_override: bool = False

    def to_dict(self) -> dict:
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "mitigation": self.mitigation,
            "allow_override": self.allow_override,
        }


@dataclass
class PreprocessingResult:
    """Result of preprocessing pipeline."""

    success: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[SecurityWarning] = field(default_factory=list)
    should_block: bool = False
    metadata: dict = field(default_factory=dict)

    def add_error(self, error: ValidationError) -> None:
        self.errors.append(error)
        if error.severity == "error":
            self.success = False
            self.should_block = True

    def add_warning(self, warning: SecurityWarning) -> None:
        self.warnings.append(warning)
        if warning.severity in ("critical", "high") and not warning.allow_override:
            self.should_block = True

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "should_block": self.should_block,
            "metadata": self.metadata,
        }
