# Project Context (The Map)

## Tech Stack
- **Language**: Python 3.14+ (Leveraging PEP 649 for deferred annotations)
- **TUI Framework**: Textual
- **Dependency Manager**: `uv`
- **Image Rendering**: `rich-pixels` + `Pillow`
- **Gmail API**: Google API Client Library
- **Authentication**: OAuth2 with local token storage in OS Keyring
- **Storage**: SQLite for local caching (WAL mode)
- **Formatting**: `ruff`
- **Typing**: `pyright`

## Architecture
- **Identity Registry**: OS Keychain (`keyring`) for all secrets and identity metadata.
- **Discovery Flow**: Anonymous OAuth flow followed by `gmail.getProfile()` to discover identity.
- **Centralized Orchestration**: The `ShmailApp` acts as the primary lifecycle manager, responsible for session initialization (`initialize_session`), database readiness, and cross-screen coordination.
- **Service Registry Pattern**: `ShmailApp` maintains instances of core services (`AuthService`, `SyncService`, `DatabaseService`), which are accessed by UI components via `self.app`.
- **Reactive UI Flow**: UI Screens (e.g., `LoadingScreen`) and Widgets (e.g., `StatusBar`) are "dumb" reactive viewers. They do not trigger heavy logic but instead "watch" app-level reactive properties (`status_message`, `status_progress`).
- **Non-Blocking I/O (Worker Pattern)**: All blocking operations (Gmail API, SQLite) MUST run in background threads using Textual's `run_worker(thread=True)`. The UI remains responsive by `await`-ing these workers without blocking the main event loop.
- **Standardized Logging**: Every module defines a module-level logger (`logger = logging.getLogger(__name__)`). The Root logger is configured in `ShmailApp._setup_logging` with a rotating file handler and professional formatting to ensure consistent telemetry.
- **Transactional Data Pipeline**: `SyncService` coordinates with `DatabaseService` using transactional contexts (`db.transaction()`). **CRITICAL**: Network I/O (Gmail API) MUST be performed outside of transactions to prevent database locking and UI thread starvation.
- **Thread-Safe Reactive Bridge**: Updates to app-level reactive properties from background threads MUST use `app.call_from_thread()` to ensure the UI thread processes the signal and refreshes correctly.
- **Explicit Watcher Pattern**: Screens should use explicit watchers (`self.watch(self.app, ..., init=True)`) to reliably synchronize local widget state with global application state across thread boundaries.
- **Visual Focus Sovereignty**: In multi-pane layouts, the active pane MUST provide clear visual feedback (e.g., double borders via `:focus` styles) to indicate keyboard input targets.
- **User-Centric Keybindings**: Bindings are defined in a Pydantic configuration model and persisted to `config.toml`, allowing users to override defaults while maintaining universal support for Vim (j/k) and standard (Arrows/Tab) keys.
- **Code Cleanliness & Standards**:
    - **Succinct Documentation**: All classes and methods MUST have professional `"""` docstrings. Conversational or trivial comments are discouraged.
    - **Zero Metadata in Code**: No inline metadata tags (e.g., `[TODO]`, `[TICKET]`, `[PRODUCTION GRADE]`). Tracking belongs in documentation/roadmaps.
    - **Pure Styling Layer**: All visual styling (colors, weights, borders) MUST live in TCSS. No format strings or markup in Python logic unless strictly required for data sanitization.
    - **Redundancy Zero-Tolerance**: Always audit for and remove empty methods, duplicate logic, or clashing event handlers during refactoring.
- **ABSOLUTE GIT RESTRICTION**: Proactive git management (committing, adding, pushing) is strictly forbidden. The User handles all version control. Agents must never attempt to create commits.
- **Image Strategy**: "Pixels-to-characters" conversion using `rich-pixels` and half-block characters.
- **HTML Rendering**: HTML-first reading layer conversion via `inscriptis`, with canonical interaction links extracted from rendered-body markdown tokens (`markdown-it` GFM linkify).
- **Shared Markdown Contract**: Parser extraction and viewer rendering share the same markdown parser configuration to prevent interaction drift.
- **Accordion Thread UX**: Thread viewer enforces one expanded message at a time; collapsed/expanded body visibility is controlled in TCSS via `MessageItem.-expanded`.
- **Active-Link UX**: Keyboard-selected links are marked in-body via parser token injection (`【↗ label 】`). Auto-scroll during link traversal is intentionally disabled to preserve deterministic keyboard highlighting and focus behavior.

## Boundaries
- Restricted to working within the `shmail/` and `tests/` directories.
- No proactive implementation of functions or classes without user guidance.
- Do not modify `.github/` or project configuration files without permission.
