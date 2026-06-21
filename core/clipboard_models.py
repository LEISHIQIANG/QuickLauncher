"""Pure clipboard value objects shared by capture and classification."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClipboardFormatInfo:
    format_id: int
    name: str
    readable: bool
    size_hint: int = 0


@dataclass
class ClipboardSnapshot:
    sequence: int
    captured_at: float
    formats: dict[int, object] = field(default_factory=dict)
    text: str = ""
    file_paths: list[str] = field(default_factory=list)
    html: str = ""
    rtf: bytes = b""
    image_info: dict = field(default_factory=dict)
    source: str = "win32"
    truncated: bool = False
    error: str = ""

    @property
    def has_image(self) -> bool:
        return bool(self.image_info and "width" in self.image_info)

    @property
    def is_empty(self) -> bool:
        return not self.text and not self.file_paths and not self.html and not self.image_info


@dataclass
class ClipboardClassification:
    kind: str
    confidence: float
    summary: str
    actions: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
