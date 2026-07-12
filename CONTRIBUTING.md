# Contributing to QuickLauncher

Thank you for your interest in contributing! This document outlines the development workflow and quality gates.

## Prerequisites

- **Python 3.12** — the project targets CPython 3.12 on Windows.
- **Windows 10 / 11** — QuickLauncher is a Windows-native desktop application built with PyQt5.

## Getting Started

```bash
# Clone and set up
git clone https://github.com/LEISHIQIANG/QuickLauncher.git
cd QuickLauncher
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

## Quality Gates

All changes must pass the following checks before merging:

### 1. Lint

```bash
ruff check core/ ui/ hooks/ services/ bootstrap/ main.py scripts/ tests/
```

### 2. Type Check

```bash
python scripts/check_mypy_progress.py
```

### 3. Tests

```bash
python -m pytest tests/ --tb=short --timeout=120 --timeout-method=thread
```

### 4. Full Release Gate

```bash
python scripts/release_gate.py
```

This runs all of the above plus:
- Broad exception audit (`audit_broad_exceptions.py`)
- i18n translation coverage (`check_i18n_coverage.py`)
- Compilation check (`compileall`)
- Release metadata validation (`check_release_artifacts.py`)
- Post-package smoke test (`post_package_smoke.py`)

## Pre-commit Hooks

Install pre-commit to run checks automatically before each commit:

```bash
pre-commit install
```

This will run:
- `black` — code formatting
- `ruff` — linting with auto-fix
- UI quality audits (hardcoded colors, grid violations, QSS radius, font consistency, etc.)

## CI/CD

All pushes and pull requests are verified by GitHub Actions (see `.github/workflows/ci.yml`). The CI pipeline includes:

| Job | Description |
|-----|-------------|
| Lint | `ruff` check on all source and test code |
| Type Check | `mypy` with zero-error requirement |
| Tests | Full `pytest` suite with coverage report |
| Release Gate | Broad exception audit, i18n coverage, compile check, and metadata validation |

## Project Structure

```
QuickLauncher/
├── core/           # Core business logic
├── ui/             # Qt UI components
├── hooks/          # System hooks (keyboard, mouse)
├── services/       # Long-running services
├── bootstrap/      # Application bootstrap and run modes
├── plugins/        # Plugin system and SDK
├── scripts/        # Build, audit, and release scripts
├── tests/          # Test suite (pytest)
├── config/         # Runtime configuration
├── assets/         # Static assets (icons, images)
└── docs/           # Documentation
```

## License

By contributing, you agree that your contributions will be licensed under the project's MIT License.
