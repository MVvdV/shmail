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
- **Service Registry Pattern**: `ShmailApp` maintains instances of core services (`AuthService`, `SyncService`, query services) plus the shared `DatabaseRepository`, which are accessed by UI components via `self.app`.
- **Repository vs Service Layering**: `DatabaseRepository` owns storage primitives only (SQL, transactions, row access). Domain services own workflow/mutation rules (`AuthService`, `SyncService`, `MessageDraftService`). Query services own read-model shaping for UI surfaces (`LabelQueryService`, `ThreadQueryService`, `ThreadViewerService`).
- **UI Query Boundary**: Screens and widgets should prefer query services over direct repository reads. New UI features should follow `UI -> service/query service -> repository -> database`.
- **Reactive UI Flow**: UI screens and widgets should remain thin viewers of app/service state. When a view begins coordinating persistence, refresh fan-out, or cross-screen state transitions, extract that orchestration into a shared service/coordinator layer.
- **Non-Blocking I/O (Worker Pattern)**: All blocking operations (Gmail API, SQLite) MUST run in background threads using Textual's `run_worker(thread=True)`. The UI remains responsive by `await`-ing these workers without blocking the main event loop.
- **Worker Freshness Discipline**: Context-sensitive worker results must not overwrite newer UI state. Use cancellation, exclusive workers, or version/selection checks whenever stale data could race with current focus.
- **Standardized Logging**: Every module defines a module-level logger (`logger = logging.getLogger(__name__)`). The Root logger is configured in `ShmailApp._setup_logging` with a rotating file handler and professional formatting to ensure consistent telemetry.
- **Transactional Data Pipeline**: `SyncService` coordinates with `DatabaseRepository` using transactional contexts (`repository.transaction()`). **CRITICAL**: Network I/O (Gmail API) MUST be performed outside of transactions to prevent database locking and UI thread starvation.
- **Sync Correctness Over Convenience**: Fallback sync paths must reconcile stale local state, cursor recovery, and idempotent replay semantics explicitly. A successful fallback is not enough if local truth can drift.
- **Thread-Safe Reactive Bridge**: Updates to app-level reactive properties from background threads MUST use `app.call_from_thread()` to ensure the UI thread processes the signal and refreshes correctly.
- **Explicit Watcher Pattern**: Screens should use explicit watchers (`self.watch(self.app, ..., init=True)`) to reliably synchronize local widget state with global application state across thread boundaries.
- **Single Refresh Authority**: Draft, label, thread, and viewer refresh behavior should flow through a single authoritative state-change path rather than duplicated screen-local redraw choreography.
- **Local-First Mutation Contract**: Outbound-capable actions must reconcile locally first, then replay to providers later. UI surfaces should reflect local intent immediately while provider sync-back remains a separate concern.
- **Provider-Agnostic Mutation Vocabulary**: User-facing copy may say `labels`, but architecture should separate `mailbox markers`, `user labels`, and `destination container` concepts so Gmail semantics do not leak into shared mutation contracts.
- **Scope by Focus**: Main thread-list actions are thread-scoped; thread-viewer actions are message-scoped. Never expose thread-wide actions inside the thread viewer.
- **Visibility by Projection**: Local trash/spam actions must hide messages from ordinary views immediately; `TRASH` and `SPAM` act as exclusive visibility contexts unless the current view explicitly matches them.
- **Queued Send Semantics**: Sending is provisioned as a local outbox mutation, not a provider-side side effect. Drafts move from editable state to queued-outbound state and should appear in `OUTBOX`, not `SENT`, until replay exists.
- **Replay State Machine First**: Outbound/provider replay architecture should progress through explicit mutation-log states (`pending_local`, `ready_for_sync`, `in_flight`, `acked`, `failed`, `blocked`) before any live provider execution is enabled.
- **Deferred Replay Execution**: Even when replay workers and adapter registries exist, the default provider adapter should remain non-destructive until the product explicitly enables sync-back. Inspection and manual retry/block flows should work before live execution does.
- **Inline-First Feedback Rule**: Mailbox rows, thread cards, drafts, and outbox views must explain queued/failed local state directly in the main UI. Separate mutation inspection tooling is optional diagnostic support, never the primary way to understand message state.
- **Inline Recovery Rule**: When replay-relevant local state fails or blocks, retry affordances should live on the affected thread/message surfaces first. Retry/backoff metadata belongs to the mutation log infrastructure, but recovery should be understandable from the mail UI itself.
- **Thread Label Semantics**: Thread-level label actions must operate as add/remove deltas across the thread, not replace-all writes per message. Mixed-message threads may carry different labels (`INBOX`, `SENT`, categories, user labels), and thread labeling should preserve message-specific differences unless the user explicitly changes them.
- **Thread Row Contract**: Thread rows stay compact: sender/date, subject, then a two-line-capable snippet area whose last line can host right-aligned union label chips. Count/unread/failure glyphs remain in the vertical indicator rail; draft/outbox belong in label chips rather than dedicated glyphs.
- **Queued Means Outbox Only**: User-facing queued state is reserved for outbound send in `OUTBOX`. Other optimistic local mailbox mutations should appear as normal mailbox behavior unless and until replay fails or blocks.
- **Lifecycle Recovery Contract**: Sleep/wake, terminal resize, and app-focus return must be treated as first-class runtime transitions. The app should force repaint/reflow, preserve focus coherently, and avoid stale worker/network state surviving across resume boundaries.
- **Wake-Safe Sync Contract**: Periodic sync timers and provider clients must recover cleanly after suspend/resume. Stale in-flight work should be cancellable or ignorable, and provider clients should be recreatable after wake before new sync/replay work begins.
- **Lifecycle Generation Discipline**: Resume/recovery flows should bump a lifecycle generation so stale worker results from the pre-suspend world cannot repaint or overwrite resumed UI state after focus/resize/wake transitions.
- **Escalation Path For Wake Failures**: If the first recovery slice proves insufficient in manual validation, preferred escalation order is: stronger relayout/redraw command, suspend-aware sync timer restart, broader worker invalidation, then more aggressive provider/auth transport reset. Keep this sequence documented so future hardening stays deliberate rather than ad hoc.
- **Targeted Patch Strategy**: When low-flicker updates matter (for example sidebar label counts or future label edits), patch operations should flow through one state authority or query/update contract. Avoid ad hoc widget-local micro-update helpers that bypass shared state rules.
- **Visual Focus Sovereignty**: In multi-pane layouts, the active pane MUST provide clear visual feedback (e.g., double borders via `:focus` styles) to indicate keyboard input targets.
- **User-Centric Keybindings**: Bindings are defined in a Pydantic configuration model and persisted to `config.toml`, allowing users to override defaults while maintaining universal support for Vim (j/k) and standard (Arrows/Tab) keys.
- **Temporal Determinism**: Persist UTC-aware timestamps only. Parsing, normalization, ordering, and display formatting of time values must be centralized to avoid mixed naive/aware behavior and drift between widgets.
- **Code Cleanliness & Standards**:
    - **Succinct Documentation**: All public classes and methods MUST have professional `"""` docstrings with semantically correct PEP 257 imperative summary lines. Conversational or misleading summaries are defects.
    - **Zero Metadata in Code**: No inline metadata tags (e.g., `[TODO]`, `[TICKET]`, `[PRODUCTION GRADE]`). Tracking belongs in documentation/roadmaps.
    - **Pure Styling Layer**: All visual styling (colors, weights, borders) MUST live in TCSS. No format strings or markup in Python logic unless strictly required for data sanitization.
    - **Redundancy Zero-Tolerance**: Always audit for and remove empty methods, duplicate logic, or clashing event handlers during refactoring.
    - **Dead Surface Cleanup**: Dormant config keys, reactive properties, orphaned widgets, and stale roadmap assumptions must be removed or wired as part of adjacent changes.
    - **Exception Discipline**: Silent broad exception swallowing is forbidden outside narrowly justified teardown paths.
- **ABSOLUTE GIT RESTRICTION**: Proactive git management (committing, adding, pushing) is strictly forbidden. The User handles all version control. Agents must never attempt to create commits.
- **Image Strategy**: "Pixels-to-characters" conversion using `rich-pixels` and half-block characters.
- **HTML Rendering**: HTML-first reading layer conversion via `inscriptis`, with canonical interaction links extracted from rendered-body markdown tokens (`markdown-it` GFM linkify).
- **Shared Markdown Contract**: Parser extraction and viewer rendering share the same markdown parser configuration to prevent interaction drift.
- **Theme Truth**: Theme configuration and runtime theme application must converge on one source of truth. Do not maintain parallel claims of configurability while hardcoding a conflicting theme path.
- **Accordion Thread UX**: Thread viewer enforces one expanded message at a time; collapsed/expanded body visibility is controlled in TCSS via `MessageItem.-expanded`.
- **Active-Link UX**: Keyboard-selected links are marked in-body via parser token injection (`【↗ label 】`). Auto-scroll during link traversal is intentionally disabled to preserve deterministic keyboard highlighting and focus behavior.

## Boundaries
- Restricted to working within the `shmail/` and `tests/` directories.
- No proactive implementation of functions or classes without user guidance.
- Do not modify `.github/` or project configuration files without permission.
