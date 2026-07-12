"""Security audit logging for command preprocessing."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

_audit_lock = threading.Lock()


def _get_audit_log_path() -> str:
    """Get audit log file path."""
    try:
        from core.command_variables import get_config_dir

        config_dir = get_config_dir()
    except Exception:
        config_dir = "config"

    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "security_audit.log")


def log_security_event(
    event_type: str,
    severity: str,
    shortcut_id: str = "",
    shortcut_name: str = "",
    command_type: str = "",
    issue_type: str = "",
    details: str = "",
    command_preview: str = "",
    user_action: str = "",
) -> None:
    """Log a security event to audit log."""
    try:
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "severity": severity,
            "shortcut_id": shortcut_id,
            "shortcut_name": shortcut_name,
            "command_type": command_type,
            "issue_type": issue_type,
            "details": details,
            "command_preview": command_preview[:100] if command_preview else "",
            "user_action": user_action,
        }

        log_path = _get_audit_log_path()
        with _audit_lock:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


def log_validation_failure(shortcut_id: str, errors: list) -> None:
    """Log validation failure."""
    for error in errors:
        log_security_event(
            event_type="validation_failure",
            severity=error.severity if hasattr(error, "severity") else "error",
            shortcut_id=shortcut_id,
            issue_type=error.error_code if hasattr(error, "error_code") else "unknown",
            details=error.message if hasattr(error, "message") else str(error),
            user_action="blocked",
        )


def log_security_warning(shortcut_id: str, warnings: list) -> None:
    """Log security warnings."""
    for warning in warnings:
        log_security_event(
            event_type="security_warning",
            severity=warning.severity if hasattr(warning, "severity") else "medium",
            shortcut_id=shortcut_id,
            issue_type=warning.issue_type if hasattr(warning, "issue_type") else "unknown",
            details=warning.description if hasattr(warning, "description") else str(warning),
            user_action="warned",
        )


def log_rate_limit_exceeded(shortcut_id: str, limit_type: str) -> None:
    """Log rate limit exceeded."""
    log_security_event(
        event_type="rate_limit_exceeded",
        severity="medium",
        shortcut_id=shortcut_id,
        issue_type="rate_limit",
        details=f"超出速率限制: {limit_type}",
        user_action="blocked",
    )
