from __future__ import annotations

import json
from dataclasses import dataclass

from googleapiclient.errors import HttpError
from rich.style import Style
from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Select, Static

from shmail.config import settings
from shmail.services.label_state import LabelMutationResult
from shmail.widgets.shortcuts import ShortcutFooter, binding_choices_label

NO_PARENT = "__label_root__"
NO_COLOR = "__label_no_color__"

_NEUTRALS = [
    "#ffffff",
    "#f3f3f3",
    "#efefef",
    "#cccccc",
    "#999999",
    "#666666",
    "#434343",
    "#000000",
]
_REDS_PINKS = [
    "#fcdee8",
    "#fbc8d9",
    "#f7a7c0",
    "#f691b3",
    "#e07798",
    "#b65775",
    "#83334c",
    "#fcdee8",
    "#f6c5be",
    "#efa093",
    "#e66550",
    "#cc3a21",
    "#ac2b16",
    "#822111",
    "#fb4c2f",
]
_ORANGES = [
    "#ffe6c7",
    "#ffd6a2",
    "#ffbc6b",
    "#ffad47",
    "#eaa041",
    "#cf8933",
    "#a46a21",
]
_YELLOWS = [
    "#fef1d1",
    "#fce8b3",
    "#fcda83",
    "#fad165",
    "#f2c960",
    "#d5ae49",
    "#aa8831",
]
_GREENS = [
    "#c6f3de",
    "#b9e4d0",
    "#a0eac9",
    "#89d3b2",
    "#68dfa9",
    "#43d692",
    "#44b984",
    "#16a766",
    "#149e60",
    "#0b804b",
    "#2a9c68",
    "#1a764d",
    "#076239",
]
_BLUES = [
    "#c9daf8",
    "#a4c2f4",
    "#6d9eeb",
    "#4a86e8",
    "#3c78d8",
    "#285bac",
    "#1c4587",
]
_PURPLES = [
    "#e4d7f5",
    "#d0bcf1",
    "#b694e8",
    "#a479e2",
    "#8e63ce",
    "#653e9b",
    "#41236d",
]

_ORDERED_GMAIL_COLORS = [
    *_NEUTRALS,
    *_REDS_PINKS,
    *_ORANGES,
    *_YELLOWS,
    *_GREENS,
    *_BLUES,
    *_PURPLES,
]
GMAIL_ALLOWED_COLOR_VALUES: list[str] = list(dict.fromkeys(_ORDERED_GMAIL_COLORS))


@dataclass
class LabelEditorSeed:
    """Seed values used to open the label editor modal."""

    label_id: str | None = None


class LabelEditorFooter(ShortcutFooter):
    """Footer bar displaying keyboard shortcuts for label workflow."""

    version_id = "label-editor-version"
    shortcuts_id = "label-editor-shortcuts"
    show_version = False


class LabelEditScreen(ModalScreen[LabelMutationResult | None]):
    """Modal screen for creating, editing, and deleting custom labels."""

    BINDINGS = [
        Binding(settings.keybindings.close, "cancel", "Cancel", show=False),
        Binding("ctrl+s", "save", "Save Label", show=False),
        Binding(
            settings.keybindings.label_delete,
            "delete_label",
            "Delete Label",
            show=False,
        ),
    ]

    def __init__(self, seed: LabelEditorSeed | None = None) -> None:
        super().__init__(id="label-editor-screen")
        self.seed = seed or LabelEditorSeed()
        self._initial_parent_id: str | None = None
        self._can_rename = True
        self._can_delete = False
        self._active_color_select_id = "#label-editor-background-color"

    def compose(self) -> ComposeResult:
        """Render the label-management form."""
        with Vertical(id="label-editor-modal-container", classes="shmail-modal-panel"):
            with Vertical(id="label-editor-form"):
                yield Static(id="label-editor-heading")
                yield Static(
                    "Custom labels can be nested and colorized. System labels stay read-only.",
                    id="label-editor-description",
                    markup=False,
                )
                yield Input(
                    placeholder="Label name",
                    id="label-editor-name",
                    classes="shmail-form-input",
                )
                yield Select(
                    [("No parent", NO_PARENT)],
                    value=NO_PARENT,
                    allow_blank=False,
                    id="label-editor-parent",
                    classes="shmail-form-select",
                )
                yield Static("Background colour", classes="label-editor-field-label")
                yield Select(
                    self._color_select_options(),
                    value=NO_COLOR,
                    allow_blank=False,
                    id="label-editor-background-color",
                    classes="shmail-form-select",
                )
                yield Static("Text colour", classes="label-editor-field-label")
                yield Select(
                    self._color_select_options(),
                    value=NO_COLOR,
                    allow_blank=False,
                    id="label-editor-text-color",
                    classes="shmail-form-select",
                )
                yield Static("Preview", id="label-editor-preview-label")
                yield Static(id="label-editor-preview-chip")
            yield LabelEditorFooter(id="label-editor-footer")

    def on_mount(self) -> None:
        """Load current label state and initialize form defaults."""
        label_state = getattr(self.app, "label_state", None)
        if label_state is None:
            self.dismiss(None)
            return

        is_edit = self.seed.label_id is not None
        self.query_one("#label-editor-heading", Static).update(
            "Edit label" if is_edit else "New label"
        )

        current_label = label_state.get_label(self.seed.label_id) if is_edit else None
        if is_edit and current_label is None:
            self.dismiss(None)
            return

        if current_label is not None:
            self._can_rename = label_state.can_rename_label(
                str(current_label.get("id") or "")
            )
            self._can_delete = label_state.can_delete_label(
                str(current_label.get("id") or "")
            )
            full_name = str(current_label.get("name") or "")
            name_input = self.query_one("#label-editor-name", Input)
            name_input.value = full_name.split("/")[-1]
            name_input.disabled = not self._can_rename
            if self._can_rename:
                self._initial_parent_id = label_state.parent_label_id_for(
                    str(current_label.get("id") or "")
                )
            else:
                self._initial_parent_id = None
            initial_background = current_label.get("background_color")
            initial_text = current_label.get("text_color")
        else:
            self._can_rename = True
            self._can_delete = False
            initial_background = None
            initial_text = None

        parent_select = self.query_one("#label-editor-parent", Select)
        parent_options = [("No parent", NO_PARENT)]
        if self._can_rename:
            for candidate in label_state.list_parent_candidates(self.seed.label_id):
                parent_options.append(
                    (str(candidate.get("name") or ""), str(candidate.get("id") or ""))
                )
        parent_select.set_options(parent_options)
        parent_select.value = self._initial_parent_id or NO_PARENT
        parent_select.disabled = not self._can_rename

        description = (
            "Custom labels can be nested and colorized. System labels stay read-only."
            if self._can_rename or not is_edit
            else "This label name is fixed for app or provider behavior. You can still choose its colours."
        )
        self.query_one("#label-editor-description", Static).update(description)

        self.query_one(
            "#label-editor-background-color", Select
        ).value = self._color_select_value(initial_background)
        self.query_one(
            "#label-editor-text-color", Select
        ).value = self._color_select_value(initial_text)

        footer = self.query_one(LabelEditorFooter)
        footer.update_shortcuts(self.get_shortcuts())
        self._refresh_preview()
        if self._can_rename:
            self.query_one("#label-editor-name", Input).focus()
        else:
            self.query_one("#label-editor-background-color", Select).focus()

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Return footer shortcuts for the current label workflow."""
        shortcuts = [
            (binding_choices_label("ctrl+s", "Ctrl+s"), "Save"),
            (binding_choices_label(settings.keybindings.close, "q/Esc"), "Cancel"),
        ]
        if self.seed.label_id is not None and self._can_delete:
            shortcuts.append(
                (
                    binding_choices_label(
                        settings.keybindings.label_delete, "Ctrl+Shift+d"
                    ),
                    "Delete",
                )
            )
        return shortcuts

    def action_cancel(self) -> None:
        """Dismiss the editor without persisting changes."""
        self.dismiss(None)

    def action_save(self) -> None:
        """Persist label changes through the label-state authority."""
        label_state = getattr(self.app, "label_state", None)
        if label_state is None:
            self.dismiss(None)
            return

        parent_value = str(
            self.query_one("#label-editor-parent", Select).value or NO_PARENT
        )
        parent_label_id = None if parent_value == NO_PARENT else parent_value
        name = self.query_one("#label-editor-name", Input).value
        background_color = self._selected_color_value("#label-editor-background-color")
        text_color = self._selected_color_value("#label-editor-text-color")
        gmail_service = self._resolve_gmail_service()
        try:
            if self.seed.label_id is None:
                result = label_state.create_label(
                    leaf_name=name,
                    parent_label_id=parent_label_id,
                    background_color=background_color,
                    text_color=text_color,
                    gmail_service=gmail_service,
                )
                self._notify("Label created.", severity="information")
            else:
                if self._can_rename:
                    result = label_state.update_label(
                        label_id=self.seed.label_id,
                        leaf_name=name,
                        parent_label_id=parent_label_id,
                        background_color=background_color,
                        text_color=text_color,
                        gmail_service=gmail_service,
                    )
                else:
                    result = label_state.update_label_colors(
                        label_id=self.seed.label_id,
                        background_color=background_color,
                        text_color=text_color,
                        gmail_service=gmail_service,
                    )
                self._notify("Label updated.", severity="information")
        except ValueError as exc:
            self._notify(str(exc), severity="warning")
            return
        except Exception as exc:
            self._notify(
                self._format_provider_error(exc, operation="save"), severity="error"
            )
            return
        self.dismiss(result)

    def action_delete_label(self) -> None:
        """Delete the current user label when editing one."""
        if self.seed.label_id is None or not self._can_delete:
            return
        label_state = getattr(self.app, "label_state", None)
        if label_state is None:
            self.dismiss(None)
            return

        try:
            result = label_state.delete_label(
                label_id=self.seed.label_id,
                gmail_service=self._resolve_gmail_service(),
            )
        except ValueError as exc:
            self._notify(str(exc), severity="warning")
            return
        except Exception as exc:
            self._notify(
                self._format_provider_error(exc, operation="delete"), severity="error"
            )
            return
        self._notify("Label deleted.", severity="information")
        self.dismiss(result)

    @on(Input.Changed, "#label-editor-name")
    @on(Select.Changed, "#label-editor-parent")
    @on(Select.Changed, "#label-editor-background-color")
    @on(Select.Changed, "#label-editor-text-color")
    def on_form_changed(self, _event) -> None:
        """Keep the preview synchronized with current form values."""
        self._refresh_preview()

    @on(events.DescendantFocus)
    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """Ensure only the currently focused color select keeps an open overlay."""
        selector = self._resolve_color_select_owner(event.widget)
        if selector is not None:
            self._active_color_select_id = f"#{selector.id}"
            self._collapse_inactive_color_selects(
                except_selector=self._active_color_select_id
            )
            return

        focused = event.widget
        if isinstance(focused, (Input, Select)) and focused.id in {
            "label-editor-name",
            "label-editor-parent",
        }:
            self._collapse_inactive_color_selects(except_selector=None)

    def _refresh_preview(self) -> None:
        """Render the live label preview chip."""
        name = (
            self.query_one("#label-editor-name", Input).value.strip() or "Label preview"
        )
        parent_value = str(
            self.query_one("#label-editor-parent", Select).value or NO_PARENT
        )
        parent_name = ""
        label_state = getattr(self.app, "label_state", None)
        if self._can_rename and parent_value != NO_PARENT and label_state is not None:
            parent = label_state.get_label(parent_value)
            if parent is not None:
                parent_name = str(parent.get("name") or "")
        display_name = f"{parent_name}/{name}" if parent_name else name
        background_color = self._selected_color_value("#label-editor-background-color")
        text_color = self._selected_color_value("#label-editor-text-color")
        style = Style(
            bgcolor=background_color or None,
            color=text_color or None,
            bold=background_color is not None,
        )
        preview = Text(" Preview ", style=Style(dim=True))
        preview.append(f" {display_name} ", style=style)
        self.query_one("#label-editor-preview-chip", Static).update(preview)

    def _resolve_gmail_service(self):
        """Return the live Gmail service when the runtime provides one."""
        sync_service = getattr(self.app, "sync_service", None)
        if sync_service is None:
            return None
        return getattr(sync_service, "gmail", None)

    def _notify(self, message: str, *, severity: str) -> None:
        """Dispatch one notification when available."""
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(message, severity=severity)

    @staticmethod
    def _format_provider_error(exc: Exception, *, operation: str) -> str:
        """Return a concise user-facing provider error message."""
        verb = "save" if operation == "save" else "delete"
        if isinstance(exc, HttpError):
            try:
                payload = json.loads(exc.content.decode("utf-8"))
                message = str(payload.get("error", {}).get("message") or "").strip()
                if message:
                    return f"Unable to {verb} label: {message}"
            except Exception:
                pass
        message = str(exc).strip()
        if message:
            return f"Unable to {verb} label: {message}"
        return f"Unable to {verb} label right now."

    @staticmethod
    def _color_select_options() -> list[tuple[Text, str]]:
        """Return color choices with swatches and tinted hex labels."""
        options: list[tuple[Text, str]] = [(Text("No colour"), NO_COLOR)]
        for color in GMAIL_ALLOWED_COLOR_VALUES:
            swatch = Text("  ", style=Style(bgcolor=color))
            label = Text.assemble(swatch, "  ", (color, Style(color=color)))
            options.append((label, color))
        return options

    @staticmethod
    def _color_select_value(color: str | None) -> str:
        """Return one select-safe stored color value."""
        value = str(color or "").strip().lower()
        return value if value in GMAIL_ALLOWED_COLOR_VALUES else NO_COLOR

    def _selected_color_value(self, selector: str) -> str | None:
        """Return one selected color or None for the no-colour option."""
        value = str(self.query_one(selector, Select).value or NO_COLOR).strip().lower()
        return None if value == NO_COLOR else value

    def _collapse_inactive_color_selects(self, except_selector: str | None) -> None:
        """Close color-select overlays that are no longer the active field."""
        for selector in ("#label-editor-background-color", "#label-editor-text-color"):
            if except_selector is not None and selector == except_selector:
                continue
            self.query_one(selector, Select).expanded = False

    def _resolve_color_select_owner(self, widget: Widget) -> Select | None:
        """Return the owning color select for one focused descendant, if any."""
        current: Widget | None = widget
        while current is not None:
            if isinstance(current, Select) and current.id in {
                "label-editor-background-color",
                "label-editor-text-color",
            }:
                return current
            parent = current.parent
            current = parent if isinstance(parent, Widget) else None
        return None
