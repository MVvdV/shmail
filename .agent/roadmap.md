# Project Roadmap (The Memory)

## Current Status
- [x] Phase 1: Foundation & Auth (Tickets 1.1 - 1.5)
- [x] Phase 2: Gmail API & Sync (Tickets 2.1 - 2.6)
- [x] Phase 3: TUI Scaffolding - 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8
- [ ] Ticket 3.7: Resizable Sidebar (Next Action)

## Session State (Last Handover: Mar 11 2026)
- **Last Action**: Finalized LoadingScreen refinement with centralized app-level orchestration (Production-Grade). Standardized logging and verified in-file documentation protocol.
- **Next Step**: Implement **Ticket 3.7 - Resizable Sidebar**. Focus on mouse-drag event handling and keyboard resizing within the Textual architecture.
- **Blockers**: None currently identified.

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
- [ ] **Ticket 3.7**: Implement Resizable Sidebar (Mouse drag & Keyboard shortcuts).
- [x] **Ticket 3.8**: Implement `StatusBar` (Global async process feedback).

### Phase 4: Reading & Search
- [ ] **Ticket 4.1**: Implement `ReadingLayer` (Markdown rendering + Header display).
- [ ] **Ticket 4.2**: Implement `ImageWidget` (Rich Pixels pixels-to-characters).
- [ ] **Ticket 4.3**: Implement `SearchService` (SQLite FTS5 + Gmail API fallback).
- [ ] **Ticket 4.4**: Implement `SearchBar` widget (As-you-type local filtering).

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
- [ ] **Ticket 6.6**: Semantic Versioning & Automated Build Pipeline.

## Handoff Log
- [Feb 20 2026]: Established production-grade TUI architecture. Keyring storage finalized. Ready for LoadingScreen progress bar integration.
- [Mar 11 2026]: Completed Ticket 3.3 (LoadingScreen Refinement). Architected the "Centralized Orchestration" pattern. ShmailApp now manages background workers (DB init + Sync) while LoadingScreen acts as a reactive view. Codified Production-Grade and In-File Documentation mandates into the project context and Tutor persona.
