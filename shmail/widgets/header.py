from typing import TYPE_CHECKING, cast

from textual import on
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Select, Static

from shmail.config import settings
from shmail.services.auth import AuthService
from shmail.widgets.shortcuts import primary_binding_label

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class AppHeader(Horizontal):
    """The application header bar containing the logo and account information."""

    NO_ACCOUNT = "__no_account__"
    SIGN_OUT_THIS = "__sign_out_this__"
    SIGN_IN_ANOTHER = "__sign_in_another__"

    def __init__(self) -> None:
        super().__init__(id="app-header")
        self._suppress_account_select_event = False
        self._previous_focus: Widget | None = None
        self._skip_focus_restore = False

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    def compose(self):
        """Yields the logo and account controls."""
        yield Static("SHMAIL", id="app-logo")
        key = primary_binding_label(settings.keybindings.account, "A")
        with Horizontal(id="app-account-hint"):
            yield Static(key, classes="shortcut-key", markup=False)
            yield Static("Account", classes="shortcut-label", markup=False)
        yield Select[str](
            self._build_account_options(getattr(self.shmail_app, "email", "") or ""),
            value=self._current_selection_value(
                getattr(self.shmail_app, "email", "") or ""
            ),
            allow_blank=False,
            compact=True,
            id="app-account-select",
            classes="shmail-select-utility",
        )

    def on_mount(self) -> None:
        """Keep account options synchronized with app identity state."""
        account_select = cast(
            Select[str], self.query_one("#app-account-select", Select)
        )
        account_select.can_focus = False
        self.watch(account_select, "expanded", self._watch_account_expanded)

        if hasattr(type(self.shmail_app), "email"):
            self.watch(
                self.shmail_app, "email", self._update_account_options, init=True
            )
        else:
            self._update_account_options(getattr(self.shmail_app, "email", "") or "")

    def activate_account_menu(self) -> None:
        """Focus and expand account selector while preserving previous focus target."""
        account_select = cast(
            Select[str], self.query_one("#app-account-select", Select)
        )
        focused = self.app.focused
        if focused is not None and focused is not account_select:
            self._previous_focus = focused
        account_select.can_focus = True
        account_select.focus()
        if not account_select.expanded:
            account_select.action_show_overlay()

    def _watch_account_expanded(self, expanded: bool) -> None:
        """Restore prior pane focus when account menu collapses."""
        account_select = cast(
            Select[str], self.query_one("#app-account-select", Select)
        )
        if expanded:
            account_select.can_focus = True
            return

        account_select.can_focus = False
        if self._skip_focus_restore:
            self._skip_focus_restore = False
            self._previous_focus = None
            return

        target = self._previous_focus
        self._previous_focus = None
        if target is not None:
            try:
                target.focus()
                return
            except Exception:
                pass

        fallback = self._resolve_default_focus_target()
        if fallback is not None:
            fallback.focus()

    def _resolve_default_focus_target(self) -> Widget | None:
        """Resolve a stable fallback focus target from current screen."""
        query_one = getattr(self.screen, "query_one", None)
        if not callable(query_one):
            return None
        for selector in ("#labels-sidebar-list", "#threads-list"):
            try:
                widget = self.screen.query_one(selector)
                if isinstance(widget, Widget):
                    return widget
            except Exception:
                continue
        return None

    def _build_account_options(self, email: str) -> list[tuple[str, str]]:
        """Build account dropdown options with account list and account actions."""
        current_email = email.strip()
        known_accounts = AuthService().list_known_accounts()
        if current_email and current_email not in known_accounts:
            known_accounts = [current_email, *known_accounts]

        other_accounts = [item for item in known_accounts if item != current_email]
        options: list[tuple[str, str]] = []

        if current_email:
            options.append((current_email, self._account_value(current_email)))
        else:
            options.append(("No Account", self.NO_ACCOUNT))

        for account in other_accounts:
            options.append((account, self._account_value(account)))

        options.append(("Sign out of this account", self.SIGN_OUT_THIS))
        options.append(("Sign in another account", self.SIGN_IN_ANOTHER))
        return options

    @staticmethod
    def _account_value(email: str) -> str:
        """Encode an account option value from an email identity."""
        return f"acct:{email}"

    def _current_selection_value(self, email: str) -> str:
        """Return current dropdown value token for selected identity."""
        normalized = email.strip()
        if normalized:
            return self._account_value(normalized)
        return self.NO_ACCOUNT

    @staticmethod
    def _extract_account_email(value: str) -> str | None:
        """Decode account option value to email when applicable."""
        if not value.startswith("acct:"):
            return None
        email = value.removeprefix("acct:").strip()
        return email or None

    def _update_account_options(self, email: str) -> None:
        """Refresh dropdown prompt text and reset selection to current account."""
        account_select = cast(
            Select[str], self.query_one("#app-account-select", Select)
        )
        options = self._build_account_options(email)
        width_target = max(len(label) for label, _ in options) + 4
        account_select.styles.width = max(24, min(52, width_target))
        self._suppress_account_select_event = True
        account_select.set_options(options)
        account_select.value = self._current_selection_value(email)
        self._suppress_account_select_event = False

    @on(Select.Changed, "#app-account-select")
    def on_account_select_changed(self, event: Select.Changed) -> None:
        """Handle account-selector actions and guarded account switching state."""
        if self._suppress_account_select_event:
            return

        selected_value = str(event.value)
        selected_email = self._extract_account_email(selected_value)
        current_email = (getattr(self.shmail_app, "email", "") or "").strip()
        current_value = self._current_selection_value(current_email)

        if selected_value == current_value:
            return

        if selected_value == self.SIGN_OUT_THIS:
            self._skip_focus_restore = True
            self.shmail_app.sign_out_current_account()
            return

        if selected_value == self.SIGN_IN_ANOTHER:
            self._skip_focus_restore = True
            self.shmail_app.sign_in_another_account()
            return

        if selected_email and selected_email != current_email:
            notify = getattr(self.app, "notify", None)
            if callable(notify):
                notify(
                    "Account switching is disabled until multi-account routing is implemented.",
                    severity="warning",
                )
            select_widget = cast(Select[str], event.select)
            self._suppress_account_select_event = True
            select_widget.value = current_value
            self._suppress_account_select_event = False
            return

        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(
                "Account action is unavailable in the current runtime.",
                severity="warning",
            )

        select_widget = cast(Select[str], event.select)
        self._suppress_account_select_event = True
        select_widget.value = current_value
        self._suppress_account_select_event = False
