"""Central preprocessing pipeline for command validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .audit import log_rate_limit_exceeded, log_security_warning, log_validation_failure
from .errors import PreprocessingResult, SecurityWarning, ValidationError
from .rate_limiter import get_rate_limiter
from .sanitizers import sanitize_input
from .security import (
    detect_command_injection,
    detect_dangerous_patterns,
    validate_safe_path,
    validate_variable_quoting,
)
from .validators import validate_command_length, validate_path

logger = logging.getLogger(__name__)


@dataclass
class PreprocessingContext:
    """Context for preprocessing pipeline."""

    shortcut_id: str = ""
    shortcut_name: str = ""
    command: str = ""
    command_type: str = "cmd"
    working_dir: str = ""
    raw_mode: bool = False
    run_as_admin: bool = False
    param_values: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class PreprocessingPipeline:
    """Orchestrates command preprocessing validation."""

    def __init__(
        self,
        enabled: bool = True,
        strict_mode: bool = False,
        rate_limiting: bool = True,
        audit_enabled: bool = True,
        block_dangerous_patterns: bool = False,
        require_variable_quoting: bool = True,
    ):
        self.enabled = enabled
        self.strict_mode = strict_mode
        self.rate_limiting = rate_limiting
        self.audit_enabled = audit_enabled
        self.block_dangerous_patterns = block_dangerous_patterns
        self.require_variable_quoting = require_variable_quoting

    def process(self, context: PreprocessingContext) -> PreprocessingResult:
        """Execute full preprocessing pipeline."""
        result = PreprocessingResult()

        if not self.enabled:
            return result

        try:
            if not self._validate_syntax(context, result):
                return result

            if not self._validate_semantics(context, result):
                return result

            if not self._validate_security(context, result):
                return result

            if not self._validate_business_rules(context, result):
                return result

            self._audit_and_log(context, result)

        except Exception as e:
            logger.exception("Preprocessing pipeline failed: %s", e)
            result.add_error(ValidationError(field="pipeline", error_code="internal_error", message=f"预处理失败: {e}"))

        return result

    def _validate_syntax(self, context: PreprocessingContext, result: PreprocessingResult) -> bool:
        """Layer 1: Syntax validation."""
        context.command = sanitize_input(context.command)

        cmd_result = validate_command_length(context.command)
        if not cmd_result.valid:
            result.add_error(
                ValidationError(
                    field="command",
                    error_code="command_too_long",
                    message=cmd_result.error,
                    suggestion=cmd_result.suggestion,
                )
            )
            return False

        return True

    def _validate_semantics(self, context: PreprocessingContext, result: PreprocessingResult) -> bool:
        """Layer 2: Semantic validation."""
        if context.command_type not in ("cmd", "powershell", "python", "bash", "builtin"):
            result.add_error(
                ValidationError(
                    field="command_type",
                    error_code="unsupported_command_type",
                    message=f"Unsupported command type: {context.command_type}",
                    suggestion="Use cmd, powershell, python, bash, or builtin.",
                )
            )
            return False

        if context.working_dir:
            path_result = validate_path(context.working_dir, must_exist=True)
            if not path_result.valid:
                result.add_error(
                    ValidationError(
                        field="working_dir",
                        error_code="invalid_working_dir",
                        message=path_result.error,
                        suggestion=path_result.suggestion,
                    )
                )
                return False

        for param_name, param_value in context.param_values.items():
            if not param_value or not str(param_value).strip():
                result.add_error(
                    ValidationError(
                        field=f"param:{param_name}",
                        error_code="missing_required_param",
                        message=f"缺少必填参数: {param_name}",
                        suggestion="请提供参数值",
                    )
                )

        return not result.should_block

    def _validate_security(self, context: PreprocessingContext, result: PreprocessingResult) -> bool:
        """Layer 3: Security validation."""
        if context.raw_mode:
            result.metadata["raw_mode"] = True

        injection_issues = detect_command_injection(context.command, context.command_type)
        for issue in injection_issues:
            result.add_warning(
                SecurityWarning(
                    issue_type=issue.type,
                    severity=issue.severity,
                    description=issue.description,
                    mitigation=issue.mitigation,
                    allow_override=context.raw_mode or not self.strict_mode,
                )
            )

        if not context.raw_mode and self.require_variable_quoting:
            quoting_issues = validate_variable_quoting(context.command, context.command_type)
            for issue in quoting_issues:
                result.add_warning(
                    SecurityWarning(
                        issue_type=issue.type,
                        severity=issue.severity,
                        description=issue.description,
                        mitigation=issue.mitigation,
                        allow_override=not self.strict_mode,
                    )
                )

        if context.working_dir:
            path_issue = validate_safe_path(context.working_dir)
            if path_issue:
                result.add_warning(
                    SecurityWarning(
                        issue_type=path_issue.type,
                        severity=path_issue.severity,
                        description=path_issue.description,
                        mitigation=path_issue.mitigation,
                    )
                )

        pattern_issues = detect_dangerous_patterns(context.command, context.command_type)
        for issue in pattern_issues:
            result.add_warning(
                SecurityWarning(
                    issue_type=issue.type,
                    severity=issue.severity,
                    description=issue.description,
                    mitigation=issue.mitigation,
                    allow_override=not self.block_dangerous_patterns,
                )
            )

        return not result.should_block

    def _validate_business_rules(self, context: PreprocessingContext, result: PreprocessingResult) -> bool:
        """Layer 4: Business rules validation."""
        if self.rate_limiting:
            limiter = get_rate_limiter()
            allowed, reason = limiter.check_rate_limit(context.shortcut_id, context.run_as_admin)
            if not allowed:
                result.add_error(
                    ValidationError(
                        field="rate_limit",
                        error_code="rate_limit_exceeded",
                        message=reason,
                        severity="error",
                        suggestion="请稍后重试",
                    )
                )
                log_rate_limit_exceeded(context.shortcut_id, reason)
                return False

            limiter.record_execution(context.shortcut_id)

        return True

    def _audit_and_log(self, context: PreprocessingContext, result: PreprocessingResult) -> None:
        """Layer 5: Audit and logging."""
        if not self.audit_enabled:
            return

        if result.errors:
            log_validation_failure(context.shortcut_id, result.errors)

        if result.warnings:
            log_security_warning(context.shortcut_id, result.warnings)


_default_pipeline: PreprocessingPipeline | None = None


def get_pipeline() -> PreprocessingPipeline:
    """Get or create default preprocessing pipeline."""
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = PreprocessingPipeline()
    return _default_pipeline


def create_pipeline_from_settings(settings) -> PreprocessingPipeline:
    """Create preprocessing pipeline from AppSettings.

    Args:
        settings: AppSettings instance with preprocessing configuration

    Returns:
        Configured PreprocessingPipeline instance
    """
    return PreprocessingPipeline(
        enabled=getattr(settings, "preprocessing_enabled", True),
        strict_mode=getattr(settings, "preprocessing_strict_mode", False),
        rate_limiting=getattr(settings, "preprocessing_rate_limiting_enabled", True),
        audit_enabled=getattr(settings, "preprocessing_audit_enabled", True),
        block_dangerous_patterns=getattr(settings, "security_block_dangerous_patterns", False),
        require_variable_quoting=getattr(settings, "security_require_variable_quoting", True),
    )
