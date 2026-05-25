"""Shortcut file parser."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    import win32com.client  # type: ignore
    HAS_WIN32COM = True
except ImportError:
    win32com = None  # type: ignore[assignment]
    HAS_WIN32COM = False


class ShortcutParser:
    """Parse .lnk and .url shortcut files."""

    @staticmethod
    def parse(file_path: str) -> Dict[str, Any]:
        result = {
            "target": file_path,
            "args": "",
            "working_dir": "",
            "icon_location": "",
            "icon_index": 0,
        }

        if not file_path or not os.path.exists(file_path):
            return result

        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".lnk":
            return ShortcutParser._parse_lnk(file_path)
        if ext == ".url":
            return ShortcutParser._parse_url(file_path)
        return result

    @staticmethod
    def _parse_lnk(file_path: str) -> Dict[str, Any]:
        result = {
            "target": file_path,
            "args": "",
            "working_dir": "",
            "icon_location": "",
            "icon_index": 0,
        }

        parsed = ShortcutParser._parse_lnk_with_win32com(file_path)
        if parsed:
            return parsed

        parsed = ShortcutParser._parse_lnk_with_powershell(file_path)
        if parsed:
            return parsed

        return result

    @staticmethod
    def _parse_lnk_with_win32com(file_path: str) -> Dict[str, Any] | None:
        if not HAS_WIN32COM:
            return None

        try:
            shell = win32com.client.Dispatch("WScript.Shell")  # type: ignore[union-attr]
            shortcut = shell.CreateShortcut(file_path)

            result = {
                "target": shortcut.TargetPath or file_path,
                "args": shortcut.Arguments or "",
                "working_dir": shortcut.WorkingDirectory or "",
                "icon_location": "",
                "icon_index": 0,
            }

            icon_location = shortcut.IconLocation or ""
            if icon_location:
                parts = icon_location.rsplit(",", 1)
                result["icon_location"] = parts[0]
                if len(parts) > 1:
                    try:
                        result["icon_index"] = int(parts[1])
                    except ValueError:
                        pass

            return result
        except Exception as exc:
            logger.debug("win32com shortcut parse failed for %s: %s", file_path, exc)
            return None

    @staticmethod
    def _parse_lnk_with_powershell(file_path: str) -> Dict[str, Any] | None:
        escaped = file_path.replace("`", "``").replace('"', '`"')
        script = (
            f'$shell = New-Object -ComObject WScript.Shell; '
            f'$shortcut = $shell.CreateShortcut("{escaped}"); '
            f'Write-Output $shortcut.TargetPath; '
            f'Write-Output "___QL_SPLIT___"; '
            f'Write-Output $shortcut.Arguments; '
            f'Write-Output "___QL_SPLIT___"; '
            f'Write-Output $shortcut.WorkingDirectory; '
            f'Write-Output "___QL_SPLIT___"; '
            f'Write-Output $shortcut.IconLocation'
        )

        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="ignore",
            )
        except Exception as exc:
            logger.debug("PowerShell shortcut parse failed for %s: %s", file_path, exc)
            return None

        if completed.returncode != 0:
            return None

        parts = [part.strip() for part in completed.stdout.split("___QL_SPLIT___")]
        if not parts or not parts[0]:
            return None

        result = {
            "target": parts[0] or file_path,
            "args": parts[1] if len(parts) > 1 else "",
            "working_dir": parts[2] if len(parts) > 2 else "",
            "icon_location": "",
            "icon_index": 0,
        }

        icon_location = parts[3] if len(parts) > 3 else ""
        if icon_location:
            icon_bits = icon_location.rsplit(",", 1)
            result["icon_location"] = icon_bits[0]
            if len(icon_bits) > 1:
                try:
                    result["icon_index"] = int(icon_bits[1])
                except ValueError:
                    pass

        return result

    @staticmethod
    def _parse_url(file_path: str) -> Dict[str, Any]:
        result = {
            "target": file_path,
            "args": "",
            "working_dir": "",
            "icon_location": "",
            "icon_index": 0,
        }

        with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("URL="):
                    result["target"] = line[4:]
                elif line.startswith("IconFile="):
                    result["icon_location"] = line[9:]
                elif line.startswith("IconIndex="):
                    try:
                        result["icon_index"] = int(line[10:])
                    except ValueError:
                        pass

        return result
