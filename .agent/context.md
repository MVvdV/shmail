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
- **Service Orchestration**: Lazy initialization of core services (`AuthService`, `SyncService`) via `ShmailApp.initialize_session(email)`.
- **Registry Pattern**: `ShmailApp` acts as the central service registry for UI components.
- **Non-Blocking Sync**: Background workers with Textual Workers for all Gmail API I/O.
- **Image Strategy**: "Pixels-to-characters" conversion using `rich-pixels` and half-block characters.
- **HTML Rendering**: HTML to Markdown conversion via `html2text` for the reading layer.

## Boundaries
- Restricted to working within the `shmail/` and `tests/` directories.
- No proactive implementation of functions or classes without user guidance.
- Do not modify `.github/` or project configuration files without permission.
