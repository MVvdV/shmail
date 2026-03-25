Inherits From: ~/.agent/styles/python-clean.md

# Project-Specific Overrides: Python
- **Language**: Python 3.14+.
- **Dependency Manager**: `uv` exclusively. Check for `uv.lock`.
- **Formatting**: `ruff check` and `ruff format` required.
- **Typing**: Strict `pyright` checking on Pydantic models.
- **Architecture**: Dependency Injection (DI) - services accept DB instances in constructor.
- **Layering Contract**: Use `Repository` for storage primitives, `Service` for workflow/mutations, and `QueryService` for UI-facing read models. Do not blur these roles with convenience wrappers that duplicate behavior.
- **Concurrency**: `asyncio` loop or background threads with Textual Workers.
- **Time Determinism**: Persist and exchange UTC-aware timestamps only. Naive `datetime.now()` is forbidden for persisted state, sync cursors, and UI ordering logic.
- **Time Formatting**: Parsing and display formatting of timestamps must be centralized in shared helpers or view-model adapters. Do not duplicate time-formatting logic across widgets or screens.
- **Exception Discipline**: Broad silent exception swallowing (`except Exception: pass`) is forbidden outside narrowly scoped teardown paths with explicit justification.
- **UI Boundaries**: When a screen or widget starts coordinating persistence, refresh fan-out, or cross-screen state transitions, extract that orchestration into a service, coordinator, or helper instead of growing UI-owned business logic.
- **Read Boundaries**: Screens and widgets should not issue repository reads directly when a query service exists or the view requires shaped data. Route UI reads through query services so ordering/grouping rules live in one place.
- **Deterministic Sync**: Sync fallback and reconciliation paths must be explicit about stale-local cleanup, idempotency, and cursor recovery. Do not treat fallback success as equivalent to accurate reconciliation.
- **Dead Surface Policy**: Remove or wire dormant config keys, reactive properties, exported widgets, and roadmap assumptions as part of adjacent refactors. Unused surfaces are defects.
- **Docstring Standard**: Public modules, classes, and methods must use semantically correct PEP 257-style docstrings with imperative summary lines. Docstrings must describe actual behavior, not intended behavior.
- **Naming Standard**: Method and model names must reflect their domain semantics precisely. Avoid names that imply one metric or contract when the implementation mixes multiple semantics.
- **Test Focus**: Add targeted tests for race-prone and correctness-critical paths: worker overlap, autosave timers, sync fallback, timezone normalization, and mutation ordering.
