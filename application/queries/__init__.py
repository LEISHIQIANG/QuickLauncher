"""Application queries — read-side (CQRS query) handlers.

Each module is a stateless query handler that reads data through ports
and returns typed result objects. Queries never modify state.

Migration targets (from core/):
- ``core/search_service.py`` — search functionality
- ``core/pinyin_search.py`` — pinyin search
- ``core/command_registry.py`` — command lookup/discovery
- ``core/module_registry.py`` — module listing
"""

from __future__ import annotations
