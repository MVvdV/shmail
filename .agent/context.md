# Project Context (The Map)

## Tech Stack
- **Language**: Python 3.13+
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
- **Transactional Data Pipeline**: `SyncService` coordinates with `DatabaseService` using transactional contexts (`db.transaction()`) to ensure data integrity during Gmail syncs.
- **Image Strategy**: "Pixels-to-characters" conversion using `rich-pixels` and half-block characters.
- **HTML Rendering**: HTML to Markdown conversion via `html2text` for the reading layer.

## Boundaries
- Restricted to working within the `shmail/` and `tests/` directories.
- No proactive implementation of functions or classes without user guidance.
- Do not modify `.github/` or project configuration files without permission.
