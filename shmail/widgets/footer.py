from textual.containers import Horizontal
from textual.widgets import Static


class AppFooter(Horizontal):
    """The application footer bar hosting the version and shortcuts."""

    def compose(self):
        yield Static("v0.1.0", id="app-version")
        yield Horizontal(id="app-shortcuts")

    def update_shortcuts(self, shortcuts: list[tuple[str, str]]) -> None:
        """Updates the displayed shortcuts in the footer."""
        container = self.query_one("#app-shortcuts", Horizontal)
        container.remove_children()

        new_widgets = []
        for i, (key, label) in enumerate(shortcuts):
            if i > 0:
                new_widgets.append(Static("•", classes="shortcut-separator"))
            new_widgets.append(Static(key, classes="shortcut-key", markup=False))
            new_widgets.append(Static(label, classes="shortcut-label", markup=False))

        if new_widgets:
            container.mount(*new_widgets)
