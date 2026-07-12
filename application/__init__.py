"""Application use cases and ports; independent of UI and platform adapters.

Sub-packages and key modules:
- ``ports/`` — Port interfaces (Protocol classes): persistence, search, shell, UI, platform
- ``config/`` — Configuration schema, migration chain
- ``state/`` — StateStore with optimistic revision control
- ``execution/`` — Command execution model
- ``services/`` — Use case orchestration (target: shortcut_command_exec)
- ``commands/`` — CQRS write-side command handlers (target: builtin_commands, slash_commands)
- ``queries/`` — CQRS read-side query handlers (target: search_service, command_registry)
- ``errors.py`` — Stable error taxonomy (ValidationError, InfrastructureError, etc.)
- ``events.py`` — Lightweight typed event bus (Event, EventBus, event_bus)
"""
