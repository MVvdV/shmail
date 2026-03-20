# Project Roadmap (The Memory)

## Current Status
- [x] Phase 1: Foundation & Auth (Tickets 1.1 - 1.5)
- [x] Phase 2: Gmail API & Sync (Tickets 2.1 - 2.6)
- [x] Phase 3: TUI Scaffolding (Tickets 3.1 - 3.9)
- [x] Phase 4: Reading & Search (Tickets 4.1, 4.5, 4.7, 4.8, 4.9 complete)

## Session State (Last Handover: Mar 20 2026)
- **Last Action**: Completed parser/viewer parity refinements (shared markdown parser contract, no link collapsing, active-link in-body marker, accordion thread behavior, and active-link scroll sync for long messages).
- **Next Step**: Run real-inbox regression validation on long transactional threads and decide whether to add optional symbol mapping for image-link labels (parked idea) as a standalone UX enhancement ticket.
- **Blockers**: None.

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
- [ ] **Ticket 2.7**: Introduce `ProviderService` Abstraction (Protocol-Agnostic Sync Contract).
    - **Goal**: Decouple sync orchestration from Gmail-specific APIs.
    - **Scope**:
        - Define protocol-neutral provider interface (list containers, fetch messages, incremental changes, profile/cursor access).
        - Move existing Gmail implementation behind `GmailProviderService` adapter.
        - Keep `SyncService` focused on orchestration + transactions only.
    - **Acceptance Criteria**:
        - `SyncService` depends on provider contract, not Gmail API classes directly.
        - Existing Gmail sync behavior remains functionally equivalent.
- [ ] **Ticket 2.8**: Provider Capability & Cursor Model.
    - **Goal**: Normalize protocol differences (Gmail History IDs, IMAP UID/UIDVALIDITY, JMAP state tokens).
    - **Scope**:
        - Add cursor envelope persisted in metadata (`provider`, `cursor_type`, `cursor_value`, `validity`).
        - Introduce provider capability flags (`supports_threads`, `supports_push`, `supports_server_search`, `supports_labels`).
        - Update incremental sync flow to use normalized cursor API.
    - **Acceptance Criteria**:
        - Cursor storage and restore are provider-aware and migration-safe.
        - Gmail remains stable under the new model.
- [ ] **Ticket 2.9**: IMAP Provider Service (Read/Sync Foundation).
    - **Goal**: Add first non-Gmail protocol backend.
    - **Scope**:
        - Implement IMAP container/listing/fetch and incremental update strategy.
        - Normalize IMAP message payloads into the existing parser + message metadata pipeline (`body`, `body_links`, parse metadata).
        - Add capability limitations handling (threading/search variability).
    - **Acceptance Criteria**:
        - IMAP account can sync inbox and open threads in the existing TUI.
        - No regressions for Gmail accounts.
- [ ] **Ticket 2.10**: JMAP Provider Service (Read/Sync Foundation).
    - **Goal**: Add modern JSON-based protocol backend.
    - **Scope**:
        - Implement JMAP mailbox/message/thread/change adapters.
        - Map JMAP state tokens into normalized cursor model.
        - Reuse parser + message metadata flow and keep the thread viewer interaction model unchanged.
    - **Acceptance Criteria**:
        - JMAP account can sync messages and render threads with existing keyboard model.
        - Shared provider contract supports Gmail/IMAP/JMAP without per-screen branching.

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
- [x] **Ticket 4.1**: Implement Conversation Threading (Aggregated Inbox + Thread Viewer Stack).
- [ ] **Ticket 4.2**: Implement `ImageWidget` (Rich Pixels pixels-to-characters).
- [ ] **Ticket 4.3**: Implement `SearchService` (SQLite FTS5 + Gmail API fallback).
- [ ] **Ticket 4.4**: Implement `SearchBar` widget (As-you-type local filtering).
- [x] **Ticket 4.5**: UI Styling & Aesthetics Refinement (Tokyo Night borders, centered indicators, dynamic footers).
- [ ] **Ticket 4.6**: Implement Attachment Bar & Calendar Invite Cards (Standalone interactive widgets).
- [x] **Ticket 4.7**: Robust Keyboard Interaction for Message Body Links.
    - **Goal**: Enable precise keyboard focus and interaction for links/emails within the message body.
    - **Previous Attempts (Lessons Learned)**:
        - *Standard Markdown with `can_focus_children`*: Links are rendered as Rich segments, not focusable DOM widgets.
        - *Stripped MarkdownViewer*: Extra UI overhead and internal scroll hijacking (when nested in another scrollable).
        - *Virtual Cursor (Segment Tinting)*: Visually fragile and complex to synchronize with dynamic line wrapping.
        - *Source Injection (`**link**`)*: Induced visual artifacts and inconsistent highlighting.
        - *Link Picker Modal*: Functional but poor UX (detaches context from the reading flow).
    - **Implemented Direction**: Keep Markdown rendering for visual fidelity and drive interaction from persisted `body_links`, decoupled from Markdown DOM focus internals.
    - **Keyboard Contract (Locked: Mar 19 2026)**:
        - `Tab` and `f` are equivalent forward traversal actions.
        - `Shift+Tab` and `F` are equivalent reverse traversal actions.
        - Traversal is hierarchical: move across thread cards, and when a card is expanded, cycle all interactive elements inside before advancing to the next card.
        - `j/k` always enforce card-level navigation, even when focus is on an inner interactive element.
        - `Enter` on an interactive element opens the target (`http(s)` / `mailto`) without mutating focus or expansion state.
        - After external open returns, no auto-focus reassignment is performed; user remains in control.
    - **Cleanup Requirement**:
        - Remove legacy internal-link focus hacks and deprecated renderer experiments to avoid conflicting interaction behavior.
- [x] **Ticket 4.8**: Rendering Quality & Artifact Reduction.
    - **Goal**: Improve visual readability of converted message bodies while preserving deterministic keyboard interaction behavior.
    - **Scope**:
        - Standardize HTML conversion on `inscriptis` for transactional/layout-heavy emails.
        - Remove remaining parser-era artifact heuristics that are no longer needed under `inscriptis` output.
        - Keep rendered body text directly consumable by the Markdown viewer widget without extra transformation layers.
    - **Acceptance Criteria**:
        - Representative fixtures render with improved readability and reduced noise.
        - No regressions in the keyboard contract (`Tab/f`, `Shift+Tab/F`, `j/k`, `Enter`).
        - Link selection order remains deterministic and consistent with persisted `body_links` derived from rendered body text.
- [x] **Ticket 4.9**: Body Metadata Canonicalization & Legacy Cleanup.
    - **Goal**: Stabilize the persisted message-body metadata model and remove obsolete paths from prior experiments.
    - **Scope**:
        - Treat rendered `body`, rendered-body-derived `body_links`, and parse metadata fields as the canonical viewer payload.
        - Remove split link extraction paths that diverge from rendered body output.
        - Ensure parser, DB schema, and viewer read/write paths remain aligned with one interaction contract.
    - **Acceptance Criteria**:
        - No runtime references to deprecated body payload models.
        - Metadata fields are consistently populated and consumed.
        - Tests cover schema compatibility, canonical link extraction, and mouse/keyboard parity.
- [ ] **Ticket 4.10**: Archived Direction — HTML Structural Renderer.
    - **Status Note (Mar 19 2026)**: Archived/superseded by the current rendering and interaction architecture. Re-open only with explicit product direction change.
    - **Archive Rationale**:
        - Prior structural-renderer experiments introduced content loss, visual instability, and interaction complexity.
        - Current model delivers better reliability: Markdown display output + persisted interaction index.

### Phase 5: Composition & Offline
- [ ] **Ticket 5.1**: Implement `ComposeScreen` (TextArea + Recipient inputs).
- [ ] **Ticket 5.2**: Implement `DraftService` (Local auto-save + Gmail sync).
- [ ] **Ticket 5.3**: Implement `ActionQueue` (Local queuing of archive/delete actions).
- [ ] **Ticket 5.4**: Implement `ConnectivityMonitor` (Status bar heartbeats).
- [ ] **Ticket 5.5**: `MarkdownInputAdapter` for Composer (Optional Authoring Format).
    - **Goal**: Allow users to compose using markdown without coupling viewer runtime to markdown.
    - **Scope**:
        - Convert markdown authoring input into normalized compose payload for preview/edit surface.
        - Generate outbound multipart payload (`text/plain` + `text/html`) from normalized compose document.
    - **Acceptance Criteria**:
        - Markdown compose is optional and can be toggled.
        - Sent/forwarded/replied messages preserve expected formatting fidelity.
- [ ] **Ticket 5.6**: Compose Visual Parity Strategy (Editor vs Viewer Consistency).
    - **Goal**: Avoid a jarring user experience gap between compose editing and thread-view rendering.
    - **Scope**:
        - Keep compose editing reliable with plain text (`TextArea`) while preserving downstream styled rendering in viewer.
        - Define reply quoting format with nested quote depth and markdown-style quote block appearance in reader.
        - Ensure compose pipeline always has a plain-text-safe fallback for sending.
    - **Acceptance Criteria**:
        - Reply/forward outputs are readable in compose and visually coherent in thread viewer.
        - Compose-to-send pipeline remains deterministic across providers.

### Phase 7: Protocol Expansion & Account Federation
- [ ] **Ticket 7.1**: Provider Registry + Account Routing.
    - **Goal**: Support multiple accounts/providers in one app runtime.
    - **Scope**:
        - Register provider implementation per account identity.
        - Route sync/auth/send operations through provider-specific service from a shared app registry.
- [ ] **Ticket 7.2**: Protocol-Specific Send Pipeline Abstraction.
    - **Goal**: Normalize sending flow across Gmail API, IMAP/SMTP, and JMAP Submission.
    - **Scope**:
        - Add send capability interface and provider adapters.
        - Preserve draft/reply/forward behavior through a protocol-neutral compose model.

## Implementation Notes (Locked Decisions)
- Viewer runtime path uses Markdown display text for rendering and persisted `messages.body_links` derived from the rendered body as the deterministic interaction index.
- Keyboard contract remains locked: `Tab/f` forward traversal, `Shift+Tab/F` reverse traversal, `j/k` card-level traversal, `Enter` activates selected link.
- Link UX is explicit and safe: disallowed schemes remain visible/selectable, display `[blocked]` status, and produce a user-facing warning on activation attempt.
- Canonical interaction links preserve markdown token order and duplicates; collapsing links by label/href is disabled to match actual interactive token behavior.
- Message-body visibility is CSS-driven (`MessageItem.-expanded`) and thread navigation enforces strict accordion behavior (one expanded message at a time).
- Active-link visibility in long content uses persisted `line_start` metadata mapped against rendered markdown block `source_range` for scroll-into-view synchronization.
- Active keyboard link selection is rendered in-body via parser token injection using `【↗ label 】` inside the active link token.

### Phase 6: Polish & Distribution
- [ ] **Ticket 6.1**: Implement `ThemingEngine`.
- [ ] **Ticket 6.2**: Setup `Textual Pilot` tests for UI.
- [ ] **Ticket 6.3**: Configure GitHub Actions for CI/CD and PyInstaller builds.
- [ ] **Ticket 6.4**: UI Performance & Error Resilience Refinement.
- [ ] **Ticket 6.5**: Implement Graceful Logout & Session Reset (`shmail --logout`).
- [ ] **Ticket 6.6**: Cursor & Mouse Interaction Support (Hover states, custom cursors).
- [ ] **Ticket 6.7**: Semantic Versioning & Automated Build Pipeline.
- [ ] **Ticket 6.8**: Professional Packaging & Installation (`pip install`, `uv tool`, `brew`).

## Handoff Log
- [Feb 20 2026]: Established production-grade TUI architecture. Keyring storage finalized. Ready for LoadingScreen progress bar integration.
- [Mar 11 2026]: Completed Ticket 3.3 (LoadingScreen Refinement). Architected the "Centralized Orchestration" pattern. ShmailApp now manages background workers (DB init + Sync) while LoadingScreen acts as a reactive view. Codified Production-Grade and In-File Documentation mandates into the project context and Tutor persona.
- [Mar 11 2026 (Evening)]: Optimized Startup sequence with "Discovery-First" Keyring logic. Resolved frozen UI and redundant sync issues using thread-safe `call_from_thread` bridges. Finalized Phase 3 (Resizable Sidebar) and started Phase 4 (EmailViewer with Vim navigation). Upgraded project to Python 3.14.
- [Mar 14 2026]: Completed Conversation Threading (Ticket 4.1). Implemented a Modal Screen architecture for the thread viewer with a scrollable stack of message cards. Performed a massive Semantic Refactor: "Email" is now for addresses, "Message" for items, and "Thread" for conversations. Established a modular HTML-to-Markdown parser using `html2text`. Stabilized TUI navigation and dynamic shortcut footers. Documented link-interaction blockers in Ticket 4.7.
- [Mar 18 2026]: Migrated to framework v2 runtime model (`/` workflows + `@` subagents). Preserved existing system constraints (absolute git prohibition, roadmap sovereignty, cooperative tutor behavior) and retained full context/roadmap history.
- [Mar 19 2026]: Locked Ticket 4.7 keyboard interaction contract for robust mouse-free navigation: `Tab/f` forward traversal, `Shift+Tab/F` reverse traversal, `j/k` card-level override, and `Enter` link activation with no focus-state mutation on return.
- [Mar 19 2026 (Session Close)]: Closed session with roadmap sync; reaffirmed Ticket 4.10 as the active execution target, specifically HTML-first semantic block rendering with guarded plain-text fallback.
- [Mar 19 2026 (Correction)]: Session-close handoff entry above was stale. Active direction is implemented Markdown display rendering with persisted `body_links` interaction indexing. Ticket 4.10 is archived unless explicitly re-opened.
- [Mar 20 2026]: Replaced HTML conversion dependency with `inscriptis` and removed HTML-anchor merge fallback from runtime parsing. Canonical `body_links` now derive from rendered body content and drive both keyboard traversal and guarded mouse activation.
- [Mar 20 2026]: Simplified parser pipeline by removing regex-based URL/email extraction and legacy plain/html split-link paths. Canonical links are extracted from rendered body markdown tokens (`markdown-it` GFM + linkify) to keep mouse and keyboard interaction parity.
- [Mar 20 2026]: Hardened application/runtime orchestration: sidebar and thread list DB reads now run via workers, bootstrap status restoration is applied through thread-safe UI updates, periodic sync scheduling is gated to successful session initialization, and sync error handling is surfaced through status updates.
- [Mar 20 2026]: Improved sync/data hygiene by pruning stale labels during label refresh and correcting incremental `added` metrics to count only successfully fetched+parsed messages.
- [Mar 20 2026 (Session Close)]: Session workflow executed. Roadmap session state refreshed and next execution target fixed on `Ticket 4.8` regression validation (rendering quality + keyboard/link contract stability).
- [Mar 20 2026]: Removed canonical link collapsing and aligned extraction/rendering on one shared markdown parser contract (`gfm-like`), including kind metadata for lightweight link-type hints.
- [Mar 20 2026]: Added active-link visual marker injection (`【↗ label 】`) inside link tokens and kept mouse/keyboard interaction parity against persisted canonical links.
- [Mar 20 2026]: Implemented strict accordion thread behavior with CSS-driven collapsed state defaults and Textual lifecycle-safe initial thread mount/show reconciliation.
- [Mar 20 2026]: Added active-link scroll synchronization for long messages using persisted `line_start` metadata and markdown block `source_range` matching.
