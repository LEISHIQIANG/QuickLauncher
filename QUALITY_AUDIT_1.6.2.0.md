# QuickLauncher 1.6.2.0 Quality Audit Backlog

This backlog records the first deep quality pass for 1.6.2.0. It is intentionally focused on cleanup, bug risk, and release confidence rather than new product features.

## Baseline

- `ruff check core ui hooks services plugins tests` initially found 5 mechanical issues in `tests/test_icon_grid_batch_ui.py`; these were fixed.
- `mypy core ui hooks services bootstrap` currently reports 1092 pre-existing type errors. Most are caused by dynamic Qt compatibility aliases, mixin attributes, and optional Windows APIs, so mypy should remain advisory until those surfaces are typed deliberately.
- `scripts/audit_broad_exceptions.py --top 15` currently reports 1257 broad exception handlers in source scope. This is a real runtime-risk backlog, not the same category as advisory mypy debt: 920 handlers have direct logging, 9 re-raise, and 333 currently lack direct logging or re-raise.
- `scripts/release_gate.py --dry-run` confirms the local gate covers ruff, pytest, broad exception regression auditing, compileall, and release metadata.
- `scripts/release_gate.py` now includes the broad exception audit with baseline thresholds (`--max-total 1257 --max-unlogged 333`) so the release gate blocks regressions while cleanup proceeds in smaller subsystem batches.
- Ignored generated artifacts were present locally: `.coverage`, `.mypy_cache/`, `.pytest_cache/`, `htmlcov/`, `dist/`, `temp_icons/`, `hooks/hook_debug.log`, and a stray `QuickLauncher_Portable_1.6.2.0` marker.

## P0 / P1 Fix Queue

- P1: Make `mypy` actionable by narrowing its scope first. Start with `services/update`, `core/config_*`, and non-Qt command execution helpers before touching Qt-heavy mixins.
- P1: Audit broad exception handlers in startup, command execution, plugin loading, config save/recovery, update install, and autostart. Keep recoverable failures logged with diagnostic context; return explicit failure results for user-visible command paths. First reduction target: lower the 333 unlogged/no-reraise handlers without increasing the 1257 total baseline.
- P1: Re-run the full release gate after every cleanup batch because `scripts/release_gate.py` deletes stale caches before testing.

## P2 Cleanup Queue

- P2: Add repeatable audit coverage for generated artifact detection, orphaned tracked resources, and known noisy advisory checks. Broad exception auditing is now covered by `scripts/audit_broad_exceptions.py`.
- P2: Review compatibility wrappers and deprecated helpers with full-repo reference searches before removal.
- P2: Split dead-code review by subsystem: command execution, plugins, config/import/export, update, UI support windows, and build scripts.
- P2: Keep release artifacts in `dist/` out of source control; release validation should inspect them only when explicitly building a release.

## Dead Code Cleanup

- Removed internal-only helpers with no production references: `TrayApp._test_popup`, `TrayApp._force_unload_dlls`, `IconGrid.handle_reorder`, and `IconGrid._add_from_file`.
- Kept deprecated/compatibility surfaces that may be external or upgrade-path API: clipboard compatibility wrapper, legacy config import/export, Windows service cleanup facade, Qt event handlers, plugin APIs, and command registry entries.

## P3 Follow-Ups

- P3: Document why full mypy is advisory in the contributor guide until the dynamic Qt/mixin layer is typed.
- P3: Consider a non-blocking CI audit job for dead-code and artifact checks once the local script is stable.
