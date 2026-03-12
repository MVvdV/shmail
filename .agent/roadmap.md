# Project Roadmap (The Memory)

## Current Status
- [x] Phase 1: Foundation & Auth (Tickets 1.1 - 1.5)
- [x] Phase 2: Gmail API & Sync (Tickets 2.1 - 2.6)
- [x] Phase 3: TUI Scaffolding (Tickets 3.1 - 3.9)
- [x] Phase 4: Reading & Search (Ticket 4.1 complete)
- [ ] Ticket 4.5: UI Styling Refinement (Next Action)

## Session State (Last Handover: Mar 11 2026)
- **Last Action**: Finalized Phase 3 and initiated Phase 4. Implemented Resizable Sidebar (Ticket 3.7) and EmailViewer (Ticket 4.1). Resolved critical async bottlenecks in the startup and sync sequence using thread-safe reactive bridges.
- **Next Step**: Implement **Ticket 4.5 - UI Styling Refinement**. Focus on improving the visual hierarchy, padding, and border styles across the MainScreen and EmailViewer to achieve a more polished, production-grade look.
- **Blockers**: None. Gmail Sync and TUI Navigation are fully operational.

## Granular Tickets (Migrated)

### Phase 1: Foundation & Auth
- [x] **Ticket 1.1**: Setup `pyproject.toml` and directory structure.
- [x] **Ticket 1.2**: Implement `config.py` (Settings management via Pydantic/TOML).
- [x] **Ticket 1.3**: Implement `auth.py` (OAuth2 loopback flow & OS Keyring integration).
- [x] **Ticket 1.4**: Implement `db.py` (SQLite initialization, WAL mode, and migrations).
- [x] **Ticket 1.5**: Implement `models.py` (Email, Thread, and Label data structures).

### Phase 2: Gmail API & Sync
- [x] **Ticket 2.1**: Implement `GmailService` (Base API wrapper).
- [x] **Ticket 2.2**: Implement `SyncService.initial_sync` (Fetch last 500 messages).
- [x] **Ticket 2.3**: Implement `LabelSyncService` (Syncing and mapping Gmail labels).
- [x] **Ticket 2.4**: Implement `SyncService.incremental_sync` (Gmail History API).
- [x] **Ticket 2.5**: Implement `MessageParser` (Unified MIME parsing for Email & Contacts).
- [x] **Ticket 2.6**: Refactor `SyncService` & `DatabaseService` into a Transactional Pipeline.

### Phase 3: TUI Scaffolding
- [x] **Ticket 3.1**: Create `app.py` and base `ShmailApp` with `shmail.tcss`.
- [x] **Ticket 3.2**: Implement `LoginScreen` (OAuth trigger and Welcome splash).
- [x] **Ticket 3.3**: Implement `LoadingScreen` (DB Initialization & Progress feedback).
- [x] **Ticket 3.4**: Implement `MainScreen` (Container for Sidebar & EmailList).
- [x] **Ticket 3.5**: Implement `Sidebar` widget (Label navigation).
- [x] **Ticket 3.6**: Implement `EmailList` widget (Message snippets).
- [x] **Ticket 3.7**: Implement Resizable Sidebar (Mouse drag & Keyboard shortcuts).
- [x] **Ticket 3.8**: Implement `StatusBar` (Global async process feedback).
- [x] **Ticket 3.9**: Implement Advanced Navigation & Config-Driven Bindings (Arrows, Focus, Config).

### Phase 4: Reading & Search
- [x] **Ticket 4.1**: Implement `EmailViewer` (Markdown rendering + Header display).
- [ ] **Ticket 4.2**: Implement `ImageWidget` (Rich Pixels pixels-to-characters).
- [ ] **Ticket 4.3**: Implement `SearchService` (SQLite FTS5 + Gmail API fallback).
- [ ] **Ticket 4.4**: Implement `SearchBar` widget (As-you-type local filtering).
- [ ] **Ticket 4.5**: UI Styling & Aesthetics Refinement (Borders, Padding, and Hierarchy).

### Phase 5: Composition & Offline
- [ ] **Ticket 5.1**: Implement `ComposeScreen` (TextArea + Recipient inputs).
- [ ] **Ticket 5.2**: Implement `DraftService` (Local auto-save + Gmail sync).
- [ ] **Ticket 5.3**: Implement `ActionQueue` (Local queuing of archive/delete actions).
- [ ] **Ticket 5.4**: Implement `ConnectivityMonitor` (Status bar heartbeats).

### Phase 6: Polish & Distribution
- [ ] **Ticket 6.1**: Implement `ThemingEngine`.
- [ ] **Ticket 6.2**: Setup `Textual Pilot` tests for UI.
- [ ] **Ticket 6.3**: Configure GitHub Actions for CI/CD and PyInstaller builds.
- [ ] **Ticket 6.4**: UI Performance & Error Resilience Refinement.
- [ ] **Ticket 6.5**: Implement Graceful Logout & Session Reset (`shmail --logout`).
- [ ] **Ticket 6.6**: Cursor & Mouse Interaction Support (Hover states, custom cursors).
- [ ] **Ticket 6.7**: Semantic Versioning & Automated Build Pipeline.

## Handoff Log
- [Feb 20 2026]: Established production-grade TUI architecture. Keyring storage finalized. Ready for LoadingScreen progress bar integration.
- [Mar 11 2026]: Completed Ticket 3.3 (LoadingScreen Refinement). Architected the "Centralized Orchestration" pattern. ShmailApp now manages background workers (DB init + Sync) while LoadingScreen acts as a reactive view. Codified Production-Grade and In-File Documentation mandates into the project context and Tutor persona.
- [Mar 11 2026 (Evening)]: Optimized Startup sequence with "Discovery-First" Keyring logic. Resolved frozen UI and redundant sync issues using thread-safe `call_from_thread` bridges. Finalized Phase 3 (Resizable Sidebar) and started Phase 4 (EmailViewer with Vim navigation). Upgraded project to Python 3.14.
