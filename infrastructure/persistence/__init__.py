"""Infrastructure persistence layer — data storage and retrieval adapters.

This package implements the storage ports defined in ``application/ports/``.
All file I/O, JSON serialization, backup, and migration logic lives here.

Adapters:
- ``adapters.ConfigRepositoryAdapter`` — wraps ``ConfigDataStore`` → ``ConfigRepository``
- ``adapters.BackupStoreAdapter`` — wraps ``ConfigBackupService`` → ``BackupStore``
- ``adapters.HistoryStoreAdapter`` — wraps ``ConfigHistoryManager`` → ``HistoryStore``

Migration targets (from core/):
- ``core/data_loader.py`` — loading configuration from disk
- ``core/save_coordinator.py`` — save coordination (batch + debounce)
- ``core/config_validation.py`` — config validation on load
- ``core/icon_repository.py`` — favicon/icon repository
- ``core/backup_service.py`` — configuration backup

Schema migrations live in ``application/config/schema.py`` and are
referenced from this layer during load time.
"""

from __future__ import annotations
