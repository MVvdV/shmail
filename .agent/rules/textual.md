Inherits From: ~/.agent/styles/textual.md

# Project-Specific Overrides: Textual
- **Layout Architecture**: Use the "Modern Triage" layered approach (dynamic, layered layers rather than narrow panes).
- **Navigation**:
    - **AppHeader**: Top breadcrumb-style indicator (`Shmail > Inbox`).
    - **Status Feedback**: Global async feedback should flow through the active screen/footer architecture or another mounted runtime surface that actually exists in the app. Do not document or depend on orphaned widgets.
- **Custom Patterns**:
    - Layered UI reading layer (dedicated layer swaps).
    - Toggleable sidebar (shortcut `b`).
    - Standardized logging (`getLogger(__name__)`).
- **Styling**: All styling should be localized to the project and not part of the global standards.
- **Blocking Work**: Gmail calls, SQLite reads/writes, and other blocking I/O must run via Textual workers or equivalent background execution with explicit UI-thread handoff.
- **Stale Result Safety**: Worker-driven loads must guard against stale results overwriting newer UI state. Use exclusive workers, cancellation, or selection/version checks when data is context-sensitive.
- **Refresh Authority**: Draft/thread/sidebar/list refreshes should flow through one authoritative state-change path. Avoid duplicated screen-local redraw choreography.
- **Pattern Reuse**: Repeated modal chooser, footer shortcut, focus-owner, and list-action structures should be extracted into shared UI helpers before divergence grows.
- **Theme Truth**: Runtime theme configuration must map to the actual app theme. Avoid parallel systems where config claims theming flexibility while TCSS or app code hardcodes a separate source of truth.
- **Capability Honesty**: Interactive controls must reflect real capability. If account switching, mutations, or similar flows are intentionally disabled, the UX must communicate that truth without implying completion.
- **Keyboard Contract**: Locked keyboard behaviors require explicit Textual Pilot coverage before refactors that touch focus, traversal, or modal layering.
