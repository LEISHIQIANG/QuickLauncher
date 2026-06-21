"""Wire up FolderPanelDragMixin using line-span removal."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PANEL = ROOT / "ui" / "config_window" / "folder_panel.py"
MIXIN = ROOT / "ui" / "config_window" / "folder_panel_drag.py"

text = PANEL.read_text(encoding="utf-8")
lines = text.split("\n")

# Get method names from the mixin
DRAG_METHODS = set()
for line in MIXIN.read_text(encoding="utf-8").split("\n"):
    m = re.match(r"    def (\w+)\(", line)
    if m:
        DRAG_METHODS.add(m.group(1))

print(f"Drag methods: {sorted(DRAG_METHODS)}")

# Build a list of all method spans
# Each entry: (start_line, end_line_exclusive, name)
method_spans = []
current_name = None
current_start = None
for i, line in enumerate(lines):
    m = re.match(r"    def (\w+)\(", line)
    if m:
        if current_name:
            method_spans.append((current_start, i, current_name))
        current_name = m.group(1)
        current_start = i
if current_name:
    method_spans.append((current_start, len(lines), current_name))

# Find spans to remove
lines_to_remove = set()
for start, end, name in method_spans:
    if name in DRAG_METHODS:
        for i in range(start, end):
            lines_to_remove.add(i)
        print(f"  Remove {name}: L{start+1}-L{end} ({end-start} lines)")

# Build new file
new_lines = [line for i, line in enumerate(lines) if i not in lines_to_remove]
result = "\n".join(new_lines)

# Add mixin
result = result.replace("class FolderPanel(QWidget):", "class FolderPanel(FolderPanelDragMixin, QWidget):")

# Add import before folder_panel_widgets import
result = result.replace(
    "from .folder_panel_widgets import (",
    "from .folder_panel_drag import FolderPanelDragMixin\n\nfrom .folder_panel_widgets import (",
)

PANEL.write_text(result, encoding="utf-8")
new_count = result.count("\n") + 1
print(f"Updated: {new_count} lines (-{len(lines) - new_count})")

# Verify
from ui.config_window.folder_panel import FolderPanel  # noqa: E402

print(f"MRO: {[c.__name__ for c in FolderPanel.__mro__]}")
print("Done!")
