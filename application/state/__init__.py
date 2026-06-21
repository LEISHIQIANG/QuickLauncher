"""Single-writer state and immutable application snapshots."""

from .store import AppSnapshot, StateStore

__all__ = ["AppSnapshot", "StateStore"]
