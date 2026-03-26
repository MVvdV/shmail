from __future__ import annotations

import json
from colorsys import rgb_to_hsv
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
SWATCHES_PER_ROW = 18

_RAW_GMAIL_ALLOWED_COLOR_VALUES: list[str] = [
    "#000000",
    "#434343",
    "#666666",
    "#999999",
    "#CCCCCC",
    "#EFEFEF",
    "#F3F3F3",
    "#FFFFFF",
    "#FB4C2F",
    "#FFAD47",
    "#FAD165",
    "#16A766",
    "#43D692",
    "#4A86E8",
    "#A479E2",
    "#F691B3",
    "#F6C5BE",
    "#FFE6C7",
    "#FEF1D1",
    "#B9E4D0",
    "#C6F3DE",
    "#C9DAF8",
    "#E4D7F5",
    "#FCDEE8",
    "#EFA093",
    "#FFD6A2",
    "#FCE8B3",
    "#89D3B2",
    "#A0EAC9",
    "#A4C2F4",
    "#D0BCF1",
    "#FBC8D9",
    "#E66550",
    "#FFBC6B",
    "#FCDA83",
    "#44B984",
    "#68DFA9",
    "#6D9EEB",
    "#B694E8",
    "#F7A7C0",
    "#CC3A21",
    "#EAA041",
    "#F2C960",
    "#149E60",
    "#3DC789",
    "#3C78D8",
    "#8E63CE",
    "#E07798",
    "#AC2B16",
    "#CF8933",
    "#D5AE49",
    "#0B804B",
    "#2A9C68",
    "#285BAC",
    "#653E9B",
    "#B65775",
    "#822111",
    "#A46A21",
    "#AA8831",
    "#076239",
    "#1A764D",
    "#1C4587",
    "#41236D",
    "#83334C",
    "#464646",
    "#E7E7E7",
    "#0D3472",
    "#B6CFF5",
    "#0D3B44",
    "#98D7E4",
    "#3D188E",
    "#E3D7FF",
    "#711A36",
    "#FBD3E0",
    "#8A1C0A",
    "#F2B2A8",
    "#7A2E0B",
    "#FFC8AF",
    "#7A4706",
    "#FFDEB5",
    "#594C05",
    "#FBE983",
    "#684E07",
    "#FDEDC1",
    "#0B4F30",
    "#B3EFD3",
    "#04502E",
    "#A2DCC1",
    "#C2C2C2",
    "#4986E7",
    "#2DA2BB",
    "#B99AFF",
    "#994A64",
    "#F691B2",
    "#FF7537",
    "#FFAD46",
    "#662E37",
    "#EBDBDE",
    "#CCA6AC",
    "#094228",
    "#42D692",
    "#16A765",
]


def _sort_color_spectrum(colors: list[str]) -> list[str]:
    """Return the documented Gmail colors ordered roughly by spectrum."""

    def sort_key(hex_color: str) -> tuple[int, float, float, float]:
        red = int(hex_color[1:3], 16) / 255
        green = int(hex_color[3:5], 16) / 255
        blue = int(hex_color[5:7], 16) / 255
        hue, saturation, value = rgb_to_hsv(red, green, blue)
        is_neutral = 0 if saturation < 0.08 else 1
        return (is_neutral, hue, value, saturation)

    return sorted(colors, key=sort_key)


GMAIL_ALLOWED_COLOR_VALUES: list[str] = _sort_color_spectrum(
    _RAW_GMAIL_ALLOWED_COLOR_VALUES
)


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
        super().__init__(label, markup=False, classes="label-color-swatch")
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
        super().__init__(id="label-color-grid")
        self.cursor_index = 0
        self.mode = BACKGROUND_MODE
        self.selected_background_color: str | None = None
        self.selected_text_color: str | None = None

    def compose(self) -> ComposeResult:
        """Render the no-color row and responsive multi-column swatch rows."""
        with Vertical(id="label-color-grid-body"):
            yield LabelColorSwatch(0, "No colour", None)
            for row_start in range(
                0, len(GMAIL_ALLOWED_COLOR_VALUES), SWATCHES_PER_ROW
            ):
                with Horizontal(classes="label-color-row"):
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
        self.selected_background_color = background_color
        self.selected_text_color = text_color
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
        super().__init__()
        self.seed = seed or LabelEditorSeed()
        self._initial_parent_id: str | None = None
        self._selection_mode = BACKGROUND_MODE

    def compose(self) -> ComposeResult:
        """Render the label-management form."""
        with Vertical(id="label-editor-modal-container"):
            with Vertical(id="label-editor-header-fields"):
                yield Static(id="label-editor-title")
                yield Static(
                    "Custom labels can be nested and colorized. System labels stay read-only.",
                    id="label-editor-subtitle",
                    markup=False,
                )
                yield Input(placeholder="Label name", id="label-name")
                yield Select[str](
                    [("No parent", NO_PARENT)],
                    value=NO_PARENT,
                    allow_blank=False,
                    id="label-parent",
                )
                yield Static(id="label-color-mode")
                yield Static("Preview", id="label-preview-title")
                yield Static(id="label-preview")
            with ScrollableContainer(id="label-color-scroll"):
                yield LabelColorGrid()
            yield LabelEditorFooter(id="label-editor-footer")

    def on_mount(self) -> None:
        """Load current label state and initialize form defaults."""
        label_state = getattr(self.app, "label_state", None)
        if label_state is None:
            self.dismiss(None)
            return

        is_edit = self.seed.label_id is not None
        self.query_one("#label-editor-title", Static).update(
            "Edit label" if is_edit else "New label"
        )

        current_label = label_state.get_label(self.seed.label_id) if is_edit else None
        if is_edit and current_label is None:
            self.dismiss(None)
            return

        if current_label is not None:
            full_name = str(current_label.get("name") or "")
            self.query_one("#label-name", Input).value = full_name.split("/")[-1]
            self._initial_parent_id = label_state.parent_label_id_for(
                str(current_label.get("id") or "")
            )
            initial_background = current_label.get("background_color")
            initial_text = current_label.get("text_color")
        else:
            initial_background = None
            initial_text = None

        parent_select = self.query_one("#label-parent", Select)
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
        self.query_one("#label-name", Input).focus()

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

        parent_value = str(self.query_one("#label-parent", Select).value or NO_PARENT)
        parent_label_id = None if parent_value == NO_PARENT else parent_value
        name = self.query_one("#label-name", Input).value
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

    @on(Input.Changed, "#label-name")
    @on(Select.Changed, "#label-parent")
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
        self.query_one("#label-color-mode", Static).update(
            f"Editing: {target} ({toggle} to toggle)"
        )

    def _refresh_preview(self) -> None:
        """Render the live label preview chip."""
        name = self.query_one("#label-name", Input).value.strip() or "Label preview"
        parent_value = str(self.query_one("#label-parent", Select).value or NO_PARENT)
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
        self.query_one("#label-preview", Static).update(preview)

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
