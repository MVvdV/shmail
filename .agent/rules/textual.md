Inherits From: ~/.agent/styles/textual.md

# Project-Specific Overrides: Textual
- **Layout Architecture**: Use the "Modern Triage" layered approach (dynamic, layered layers rather than narrow panes).
- **Navigation**:
    - **AppHeader**: Top breadcrumb-style indicator (`Shmail > Inbox`).
    - **StatusBar**: Persistent widget watching the `status_message` property for global async feedback.
- **Custom Patterns**:
    - Layered UI reading layer (dedicated layer swaps).
    - Toggleable sidebar (shortcut `b`).
    - Standardized logging (`getLogger(__name__)`).
- **Styling**: All styling should be localized to the project and not part of the global standards.
