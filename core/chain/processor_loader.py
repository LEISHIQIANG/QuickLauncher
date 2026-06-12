"""Processor loader and discovery for action chains.

This module provides:
- Auto-discovery of processors from modules
- Loading processors from files
- Processor validation and registration
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from pathlib import Path
from typing import Any

from .definitions import ChainProcessorDefinition
from .processor_registry import ProcessorRegistry, get_registry

__all__ = [
    "ProcessorLoader",
    "discover_processors",
    "load_processors_from_module",
    "load_processors_from_directory",
]


logger = logging.getLogger(__name__)


class ProcessorLoader:
    """Loader for discovering and registering processors."""

    def __init__(self, registry: ProcessorRegistry | None = None):
        self._registry = registry or get_registry()
        self._loaded_modules: set[str] = set()

    @property
    def registry(self) -> ProcessorRegistry:
        """Get the processor registry."""
        return self._registry

    # ── Module Discovery ───────────────────────────────────────────────────

    def discover_from_module(self, module_name: str) -> int:
        """Discover and register processors from a Python module.

        The module should have either:
        - A `get_processors()` function that returns dict[str, ChainProcessorDefinition]
        - A `PROCESSORS` dict containing processor definitions
        - A `register_processors(registry)` function

        Args:
            module_name: Python module name (e.g., 'core.chain.additional_processors')

        Returns:
            Number of processors registered
        """
        if module_name in self._loaded_modules:
            return 0

        try:
            module = importlib.import_module(module_name)
            count = self._register_from_module(module)
            self._loaded_modules.add(module_name)
            return count
        except Exception as e:
            logger.error("Failed to load processors from %s: %s", module_name, e)
            return 0

    def _register_from_module(self, module: Any) -> int:
        """Register processors from a module."""
        count = 0

        # Try get_processors() function
        if hasattr(module, "get_processors") and callable(module.get_processors):
            processors = module.get_processors()
            if isinstance(processors, dict):
                for _proc_id, definition in processors.items():
                    if isinstance(definition, ChainProcessorDefinition):
                        if self._registry.register(definition):
                            count += 1

        # Try PROCESSORS dict
        elif hasattr(module, "PROCESSORS") and isinstance(module.PROCESSORS, dict):
            for _proc_id, definition in module.PROCESSORS.items():
                if isinstance(definition, ChainProcessorDefinition):
                    if self._registry.register(definition):
                        count += 1

        # Try register_processors(registry) function
        elif hasattr(module, "register_processors") and callable(module.register_processors):
            result = module.register_processors(self._registry)
            if isinstance(result, int):
                count = result

        return count

    def discover_from_package(self, package_name: str) -> int:
        """Discover processors from all modules in a package.

        Args:
            package_name: Python package name

        Returns:
            Total number of processors registered
        """
        try:
            package = importlib.import_module(package_name)
            package_path = getattr(package, "__path__", None)

            if not package_path:
                return self.discover_from_module(package_name)

            total = 0
            for module_info in sorted(pkgutil.iter_modules(package_path), key=lambda info: info.name):
                if module_info.ispkg or module_info.name.startswith("_"):
                    continue
                module_name = f"{package_name}.{module_info.name}"
                total += self.discover_from_module(module_name)

            return total
        except Exception as e:
            logger.error("Failed to discover processors from package %s: %s", package_name, e)
            return 0

    # ── Directory Discovery ────────────────────────────────────────────────

    def discover_from_directory(self, directory: str | Path) -> int:
        """Discover processors from Python files in a directory.

        Args:
            directory: Directory path to scan

        Returns:
            Number of processors registered
        """
        directory = Path(directory)
        if not directory.exists():
            return 0

        total = 0
        for file_path in directory.glob("*.py"):
            if file_path.name.startswith("_"):
                continue

            try:
                # Convert file path to module name
                module_name = file_path.stem

                # Load module from file
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    count = self._register_from_module(module)
                    total += count
            except Exception as e:
                logger.warning("Failed to load processors from %s: %s", file_path, e)

        return total

    # ── Built-in Discovery ─────────────────────────────────────────────────

    def discover_builtins(self) -> int:
        """Discover and register all built-in processors.

        Returns:
            Number of processors registered
        """
        total = 0

        # Load from main registry
        from .registry import PROCESSOR_DEFINITIONS

        for _proc_id, definition in PROCESSOR_DEFINITIONS.items():
            if self._registry.register(definition):
                total += 1

        # Load additional processors
        try:
            from .additional_processors import register_additional_processors

            count = register_additional_processors(self._registry)
            total += count
        except Exception as e:
            logger.warning("Failed to load additional processors: %s", e)

        return total

    # ── Validation ─────────────────────────────────────────────────────────

    def validate_all(self) -> list[dict[str, Any]]:
        """Validate all registered processors.

        Returns:
            List of validation issues
        """
        issues = []

        for definition in self._registry.iter_definitions():
            try:
                self._registry._validate_definition(definition)
            except ValueError as e:
                issues.append(
                    {
                        "processor_id": definition.id,
                        "error": str(e),
                    }
                )

        return issues


# ── Convenience Functions ──────────────────────────────────────────────────

_global_loader: ProcessorLoader | None = None


def get_loader() -> ProcessorLoader:
    """Get the global processor loader."""
    global _global_loader
    if _global_loader is None:
        _global_loader = ProcessorLoader()
    return _global_loader


def discover_processors() -> int:
    """Discover and register all available processors.

    Returns:
        Total number of processors registered
    """
    loader = get_loader()
    total = 0

    # Load built-ins
    total += loader.discover_builtins()

    # Try to load from additional modules
    modules_to_try = [
        "core.chain.additional_processors",
        "plugins.chain_processors",
    ]

    for module_name in modules_to_try:
        try:
            count = loader.discover_from_module(module_name)
            total += count
        except Exception as exc:
            logger.debug("发现处理器模块失败: %s", exc, exc_info=True)

    return total


def load_processors_from_module(module_name: str) -> int:
    """Load processors from a specific module."""
    return get_loader().discover_from_module(module_name)


def load_processors_from_directory(directory: str | Path) -> int:
    """Load processors from a directory."""
    return get_loader().discover_from_directory(directory)
