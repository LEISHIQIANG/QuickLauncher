"""Standalone helpers extracted from shortcut_command_exec — atomic write, launcher globals."""

from __future__ import annotations

import logging
import os
import tempfile

logger = logging.getLogger(__name__)


def _write_atomic(path: str, content: str) -> None:
    """Write content to path atomically via tempfile + rename to avoid races."""
    dir_name = os.path.dirname(path)
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix=os.path.splitext(path)[1],
            dir=dir_name if dir_name else None,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(fd)
        os.replace(tmp_path, path)
        tmp_path = None
    except Exception:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except Exception as exc:
                logger.debug("删除临时文件失败: %s", exc, exc_info=True)
        raise
