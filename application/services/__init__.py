"""Application services — use case orchestration.

Services in this package coordinate domain objects and infrastructure
adapters to fulfill a single user-facing use case. They are invoked by
UI controllers or command handlers and NEVER call UI code directly.

Migration targets (from core/):
- ``core/shortcut_command_exec.py`` — shortcut/command execution orchestration
- ``core/command_execution_service.py`` — command execution service
- ``core/action_chain_host.py`` — action chain host
- ``core/save_coordinator.py`` — save coordination
"""

from __future__ import annotations
