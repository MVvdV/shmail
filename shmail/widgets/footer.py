from shmail.widgets.shortcuts import ShortcutFooter


class AppFooter(ShortcutFooter):
    """The application footer bar hosting the version and shortcuts."""

    version_id = "app-version"
    shortcuts_id = "app-shortcuts"

    def __init__(self) -> None:
        super().__init__(id="app-footer")
