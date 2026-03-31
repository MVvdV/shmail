from __future__ import annotations

import json
from dataclasses import dataclass

from googleapiclient.errors import HttpError
from rich.style import Style
from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Select, Static

from shmail.config import settings
from shmail.services.label_state import LabelMutationResult
from shmail.widgets.shortcuts import ShortcutFooter, binding_choices_label

NO_PARENT = "__label_root__"
BACKGROUND_MODE = "background"
TEXT_MODE = "text"
SWATCHES_PER_ROW = 8

_RAW_GMAIL_ALLOWED_COLOR_VALUES: list[str] = [
    "#000000",
    "#434343",
    "#666666",
    "#999999",
    "#cccccc",
    "#efefef",
    "#f3f3f3",
    "#ffffff",
    "#f6c5be",
    "#ffe6c7",
    "#fef1d1",
    "#b9e4d0",
    "#c6f3de",
    "#c9daf8",
    "#e4d7f5",
    "#fcdee8",
    "#efa093",
    "#ffd6a2",
    "#fce8b3",
    "#89d3b2",
    "#a0eac9",
    "#a4c2f4",
    "#d0bcf1",
    "#fbc8d9",
    "#e66550",
    "#ffbc6b",
    "#fcda83",
    "#44b984",
    "#68dfa9",
    "#6d9eeb",
    "#b694e8",
    "#f7a7c0",
    "#cc3a21",
    "#eaa041",
    "#f2c960",
    "#149e60",
    "#3dc789",
    "#3c78d8",
    "#8e63ce",
    "#e07798",
    "#ac2b16",
    "#cf8933",
    "#d5ae49",
    "#0b804b",
    "#2a9c68",
    "#285bac",
    "#653e9b",
    "#b65775",
    "#822111",
    "#a46a21",
    "#aa8831",
    "#076239",
    "#1a764d",
    "#1c4587",
    "#41236d",
    "#83334c",
    "#fb4c2f",
    "#ffad47",
    "#fad165",
    "#16a766",
    "#43d692",
    "#4a86e8",
    "#a479e2",
    "#f691b3",
]
GMAIL_ALLOWED_COLOR_VALUES: list[str] = _RAW_GMAIL_ALLOWED_COLOR_VALUES


@dataclass
class LabelEditorSeed:
    """Seed values used to open the label editor modal."""

    label_id: str | None = None


class LabelEditorFooter(ShortcutFooter):
    """Footer bar displaying keyboard shortcuts for label workflow."""

    version_id = "label-editor-version"
    shortcuts_id = "label-editor-shortcuts"
    show_version = False


class LabelColorSwatch(Static):
    """One visual color swatch within the label color picker."""

    def __init__(self, swatch_index: int, label: str, color: str | None) -> None:
        super().__init__(label, markup=False, classes="label-editor-palette-swatch")
        self.swatch_index = swatch_index
        self.color_value = color


class LabelColorGrid(Widget):
    """Focusable swatch grid for selecting label text and background colors."""

    can_focus = True
    BINDINGS = [
        Binding("left", "cursor_left", "Left", show=False),
        Binding("right", "cursor_right", "Right", show=False),
        Binding(settings.keybindings.up, "cursor_up", "Up", show=False),
        Binding(settings.keybindings.down, "cursor_down", "Down", show=False),
        Binding(settings.keybindings.select, "select_cursor", "Select", show=False),
    ]

    class SelectionChanged(Message):
        """Posted when the selected colors change."""

        def __init__(
            self,
            background_color: str | None,
            text_color: str | None,
            mode: str,
        ) -> None:
            super().__init__()
            self.background_color = background_color
            self.text_color = text_color
            self.mode = mode

    def __init__(self) -> None:
        super().__init__(id="label-editor-palette-grid")
        self.cursor_index = 0
        self.mode = BACKGROUND_MODE
        self.selected_background_color: str | None = None
        self.selected_text_color: str | None = None

    def compose(self) -> ComposeResult:
        """Render the no-color row and responsive multi-column swatch rows."""
        with Vertical(id="label-editor-palette-swatches"):
            yield LabelColorSwatch(0, "No colour", None)
            for row_start in range(
                0, len(GMAIL_ALLOWED_COLOR_VALUES), SWATCHES_PER_ROW
            ):
                with Horizontal(classes="label-editor-palette-row"):
                    for offset, color in enumerate(
                        GMAIL_ALLOWED_COLOR_VALUES[
                            row_start : row_start + SWATCHES_PER_ROW
                        ],
                        start=row_start + 1,
                    ):
                        yield LabelColorSwatch(offset, "A", color)

    def on_mount(self) -> None:
        """Initialize the rendered swatch styles."""
        self.refresh_swatch_styles()

    def set_mode(self, mode: str) -> None:
        """Update the active editing mode and refresh swatch indicators."""
        self.mode = mode
        self.refresh_swatch_styles()

    def set_selection(
        self, background_color: str | None, text_color: str | None
    ) -> None:
        """Set both selected colors from external state."""
        self.selected_background_color = self._normalize_color_value(background_color)
        self.selected_text_color = self._normalize_color_value(text_color)
        self.cursor_index = self._cursor_for_colors()
        self.refresh_swatch_styles()

    def selected_colors(self) -> tuple[str | None, str | None]:
        """Return the currently selected background and text colors."""
        return self.selected_background_color, self.selected_text_color

    def action_cursor_left(self) -> None:
        """Move the swatch cursor left within the current row."""
        if self.cursor_index == 0:
            return
        row, column = self._row_and_column(self.cursor_index)
        if column > 0:
            self.cursor_index -= 1
            self.refresh_swatch_styles()

    def action_cursor_right(self) -> None:
        """Move the swatch cursor right within the current row."""
        if self.cursor_index == 0:
            return
        row, column = self._row_and_column(self.cursor_index)
        row_start = row * SWATCHES_PER_ROW + 1
        row_end = min(row_start + SWATCHES_PER_ROW - 1, len(GMAIL_ALLOWED_COLOR_VALUES))
        if row_start + column < row_end:
            self.cursor_index += 1
            self.refresh_swatch_styles()

    def action_cursor_up(self) -> None:
        """Move the swatch cursor up one row."""
        if self.cursor_index == 0:
            return
        row, column = self._row_and_column(self.cursor_index)
        if row == 0:
            self.cursor_index = 0
        else:
            target = (row - 1) * SWATCHES_PER_ROW + column + 1
            self.cursor_index = min(target, len(GMAIL_ALLOWED_COLOR_VALUES))
        self.refresh_swatch_styles()

    def action_cursor_down(self) -> None:
        """Move the swatch cursor down one row."""
        if self.cursor_index == 0:
            self.cursor_index = 1
            self.refresh_swatch_styles()
            return
        row, column = self._row_and_column(self.cursor_index)
        target = (row + 1) * SWATCHES_PER_ROW + column + 1
        if target <= len(GMAIL_ALLOWED_COLOR_VALUES):
            self.cursor_index = target
        self.refresh_swatch_styles()

    def action_select_cursor(self) -> None:
        """Apply the color under the cursor to the active target."""
        if self.cursor_index == 0:
            self.selected_background_color = None
            self.selected_text_color = None
        else:
            color = GMAIL_ALLOWED_COLOR_VALUES[self.cursor_index - 1]
            if self.mode == BACKGROUND_MODE:
                self.selected_background_color = color
            else:
                self.selected_text_color = color
        self.refresh_swatch_styles()
        self.post_message(
            self.SelectionChanged(
                self.selected_background_color,
                self.selected_text_color,
                self.mode,
            )
        )

    def on_click(self, event: events.Click) -> None:
        """Select the clicked swatch using the active target mode."""
        swatch = event.widget if isinstance(event.widget, LabelColorSwatch) else None
        if swatch is None:
            return
        self.focus()
        self.cursor_index = swatch.swatch_index
        self.action_select_cursor()

    def refresh_swatch_styles(self) -> None:
        """Refresh swatch colors and selection indicators."""
        text_color = self.selected_text_color or None
        for swatch in self.query(LabelColorSwatch):
            swatch.remove_class(
                "-cursor",
                "-selected-background",
                "-selected-text",
                "-selected-both",
                "-mode-target",
            )
            if swatch.swatch_index == 0:
                swatch.styles.background = None
                swatch.styles.color = None
            else:
                swatch.styles.background = swatch.color_value
                swatch.styles.color = text_color or "#000000"

            is_background = swatch.color_value == self.selected_background_color
            is_text = swatch.color_value == self.selected_text_color
            if (
                swatch.swatch_index == 0
                and self.selected_background_color is None
                and self.selected_text_color is None
            ):
                is_background = True
                is_text = True

            if is_background and is_text:
                swatch.add_class("-selected-both")
            elif is_background:
                swatch.add_class("-selected-background")
            elif is_text:
                swatch.add_class("-selected-text")

            if (self.mode == BACKGROUND_MODE and is_background) or (
                self.mode == TEXT_MODE and is_text
            ):
                swatch.add_class("-mode-target")

            if swatch.swatch_index == self.cursor_index:
                swatch.add_class("-cursor")

    def _cursor_for_colors(self) -> int:
        """Return the best cursor location for the current mode and colors."""
        target = (
            self.selected_background_color
            if self.mode == BACKGROUND_MODE
            else self.selected_text_color
        )
        if target is None:
            return 0
        try:
            return GMAIL_ALLOWED_COLOR_VALUES.index(target) + 1
        except ValueError:
            return 0

    @staticmethod
    def _row_and_column(cursor_index: int) -> tuple[int, int]:
        """Return zero-based row and column for one color-cell index."""
        color_index = cursor_index - 1
        return color_index // SWATCHES_PER_ROW, color_index % SWATCHES_PER_ROW

    @staticmethod
    def _normalize_color_value(color: str | None) -> str | None:
        """Return one trimmed lowercase hex color or None."""
        value = str(color or "").strip()
        return value.lower() or None


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
        Binding(
            settings.keybindings.compose_preview_toggle,
            "toggle_color_mode",
            "Toggle Color Target",
            show=False,
        ),
    ]

    def __init__(self, seed: LabelEditorSeed | None = None) -> None:
        super().__init__(id="label-editor-screen")
        self.seed = seed or LabelEditorSeed()
        self._initial_parent_id: str | None = None
        self._selection_mode = BACKGROUND_MODE

    def compose(self) -> ComposeResult:
        """Render the label-management form."""
        with Vertical(id="label-editor-modal-container"):
            with Horizontal():
                with Vertical(id="label-editor-form"):
                    yield Static(id="label-editor-heading")
                    yield Static(
                        "Custom labels can be nested and colorized. System labels stay read-only.",
                        id="label-editor-description",
                        markup=False,
                    )
                    yield Input(placeholder="Label name", id="label-editor-name")
                    yield Select[str](
                        [("No parent", NO_PARENT)],
                        value=NO_PARENT,
                        allow_blank=False,
                        id="label-editor-parent",
                    )
                    yield Static(id="label-editor-palette-status")
                    yield Static("Preview", id="label-editor-preview-label")
                    yield Static(id="label-editor-preview-chip")
                with ScrollableContainer(id="label-editor-palette-pane"):
                    yield LabelColorGrid()
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
            full_name = str(current_label.get("name") or "")
            self.query_one("#label-editor-name", Input).value = full_name.split("/")[-1]
            self._initial_parent_id = label_state.parent_label_id_for(
                str(current_label.get("id") or "")
            )
            initial_background = current_label.get("background_color")
            initial_text = current_label.get("text_color")
        else:
            initial_background = None
            initial_text = None

        parent_select = self.query_one("#label-editor-parent", Select)
        parent_options = [("No parent", NO_PARENT)]
        for candidate in label_state.list_parent_candidates(self.seed.label_id):
            parent_options.append(
                (str(candidate.get("name") or ""), str(candidate.get("id") or ""))
            )
        parent_select.set_options(parent_options)
        parent_select.value = self._initial_parent_id or NO_PARENT

        color_grid = self.query_one(LabelColorGrid)
        color_grid.set_mode(self._selection_mode)
        color_grid.set_selection(
            str(initial_background) if initial_background else None,
            str(initial_text) if initial_text else None,
        )

        footer = self.query_one(LabelEditorFooter)
        footer.update_shortcuts(self.get_shortcuts())
        self._refresh_mode_status()
        self._refresh_preview()
        self.query_one("#label-editor-name", Input).focus()

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Return footer shortcuts for the current label workflow."""
        shortcuts = [
            (binding_choices_label("ctrl+s", "Ctrl+s"), "Save"),
            (
                binding_choices_label(
                    settings.keybindings.compose_preview_toggle, "F2"
                ),
                "Toggle target",
            ),
            (binding_choices_label(settings.keybindings.close, "q/Esc"), "Cancel"),
        ]
        if self.seed.label_id is not None:
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

    def action_toggle_color_mode(self) -> None:
        """Toggle whether the swatch grid edits background or text color."""
        self._selection_mode = (
            TEXT_MODE if self._selection_mode == BACKGROUND_MODE else BACKGROUND_MODE
        )
        color_grid = self.query_one(LabelColorGrid)
        color_grid.set_mode(self._selection_mode)
        self._refresh_mode_status()

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
        background_color, text_color = self.query_one(LabelColorGrid).selected_colors()
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
                result = label_state.update_label(
                    label_id=self.seed.label_id,
                    leaf_name=name,
                    parent_label_id=parent_label_id,
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
        if self.seed.label_id is None:
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
    def on_form_changed(self, _event) -> None:
        """Keep the preview synchronized with current form values."""
        self._refresh_preview()

    @on(LabelColorGrid.SelectionChanged)
    def on_color_selection_changed(
        self, _event: LabelColorGrid.SelectionChanged
    ) -> None:
        """Refresh preview after one swatch selection change."""
        self._refresh_preview()

    def _refresh_mode_status(self) -> None:
        """Render one concise status line for the active color target."""
        target = (
            "Background colour"
            if self._selection_mode == BACKGROUND_MODE
            else "Text colour"
        )
        toggle = binding_choices_label(
            settings.keybindings.compose_preview_toggle, "F2"
        )
        self.query_one("#label-editor-palette-status", Static).update(
            f"Editing: {target} ({toggle} to toggle)"
        )

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
        if parent_value != NO_PARENT and label_state is not None:
            parent = label_state.get_label(parent_value)
            if parent is not None:
                parent_name = str(parent.get("name") or "")
        display_name = f"{parent_name}/{name}" if parent_name else name
        background_color, text_color = self.query_one(LabelColorGrid).selected_colors()
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
