"""Application commands — write-side (CQRS command) handlers.

Each module contains a stateless handler that accepts a typed Command
object, coordinates with domain services, and returns a typed Result.
No UI imports allowed; infrastructure dependencies are injected via ports.

Migration targets (from core/):
- ``core/shortcut_chain_exec.py`` — chain execution command handling
- ``core/builtin_commands.py`` — built-in command handlers
- ``core/slash_commands.py`` — slash command handlers
- ``core/commands*.py`` — various command modules
"""

from __future__ import annotations
