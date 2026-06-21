"""Platform — operating-system-specific abstractions.

This package isolates platform-dependent code from the core domain and
application layers. Each sub-package corresponds to a target OS.

Sub-packages:
- ``windows/`` — Windows-specific modules (native windowing, shell API, COM)
"""

from __future__ import annotations
