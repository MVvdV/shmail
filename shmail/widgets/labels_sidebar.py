from typing import TYPE_CHECKING, cast

from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

from shmail.config import settings
from shmail.screens.label_editor import LabelEditScreen, LabelEditorSeed
from shmail.services.label_state import LabelMutationResult
from shmail.widgets.shortcuts import binding_choices_label, movement_pair_label

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class LabelHeader(ListItem):
    """A non-selectable section divider with a labeled top border."""

    def __init__(self, title: str):
        super().__init__(disabled=True)
        self.add_class("labels-sidebar-section")
        self.title = title

    def on_mount(self) -> None:
        """Sets the border title to the section name."""
        self.border_title = self.title


class LabelItem(ListItem):
    """A selectable label with hierarchical indentation."""

    def __init__(
        self,
        display_name: str,
        label_id: str,
        count: int = 0,
        depth: int = 0,
        is_last_child: bool = False,
        background_color: str | None = None,
    ):
        super().__init__()
        self.add_class("labels-sidebar-item")
        self.display_name = display_name
        self.label_id = label_id
        self.count = count
        self.depth = depth
        self.is_last_child = is_last_child
        self.background_color = background_color

    def compose(self):
        """Constructs the label text with hierarchical connectors."""
        yield Static("■" if self.background_color else " ", classes="label-color-chip")
        yield Static(self._compose_label_text(), classes="label-name", markup=False)

        count_text = f"({self.count})" if self.count > 0 else ""
        yield Static(count_text, classes="label-count", markup=False)

    def _compose_label_text(self) -> str:
        """Build the visible label text with hierarchical indentation."""
        if self.depth <= 1:
            indent = "  " * self.depth
            connector = ""
        else:
            indent = "  " * (self.depth - 1)
            connector = "└ " if self.is_last_child else "├ "

        if self.count > 0:
            self.add_class("unread")

        return f"{indent}{connector}{self.display_name}"

    def set_count(self, count: int) -> None:
        """Update count text in-place for this label row."""
        self.count = count
        if count > 0:
            self.add_class("unread")
        else:
            self.remove_class("unread")

        try:
            count_widget = self.query_one(".label-count", Static)
        except Exception:
            return
        count_widget.update(f"({count})" if count > 0 else "")

    def on_mount(self) -> None:
        """Render an optional swatch for custom Gmail label colors."""
        if not self.background_color:
            return
        try:
            swatch = self.query_one(".label-color-chip", Static)
        except Exception:
            return
        swatch.styles.color = self.background_color


class LabelsSidebar(Vertical):
    """A navigation pane for Gmail labels organized by category and hierarchy."""

    can_focus = False

    BINDINGS = [
        Binding(
            settings.keybindings.resize_narrow,
            "shrink_labels",
            "Shrink Labels",
            show=False,
        ),
        Binding(
            settings.keybindings.resize_wide,
            "expand_labels",
            "Expand Labels",
            show=False,
        ),
        Binding(settings.keybindings.up, "cursor_up", "Previous Label", show=False),
        Binding(settings.keybindings.down, "cursor_down", "Next Label", show=False),
        Binding(settings.keybindings.first, "first_label", "First Label", show=False),
        Binding(settings.keybindings.last, "last_label", "Last Label", show=False),
        Binding(settings.keybindings.label_new, "new_label", "New Label", show=False),
        Binding(
            settings.keybindings.label_edit, "edit_label", "Edit Label", show=False
        ),
    ]

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Return the active shortcuts for the labels pane."""
        shortcuts = [
            (binding_choices_label(settings.keybindings.select, "ENTER"), "Select"),
            (
                movement_pair_label(settings.keybindings.up, settings.keybindings.down),
                "Move",
            ),
            (
                f"{binding_choices_label(settings.keybindings.first, 'G')}/{binding_choices_label(settings.keybindings.last, 'SHIFT+G')}",
                "Home/End",
            ),
            (binding_choices_label(settings.keybindings.pane_next, "TAB"), "Threads"),
            (
                f"{binding_choices_label(settings.keybindings.resize_narrow, '[')}/{binding_choices_label(settings.keybindings.resize_wide, ']')}",
                "Resize",
            ),
        ]
        if self._current_cursor_label_is_editable():
            shortcuts.insert(
                1,
                (
                    binding_choices_label(settings.keybindings.label_edit, "e"),
                    "Edit label",
                ),
            )
        return shortcuts

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    class LabelSelected(Message):
        """Sent when a label is activated in the list."""

        def __init__(self, label_id: str) -> None:
            self.label_id = label_id
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.label_list = ListView(id="labels-sidebar-list")
        self._active_label_id: str | None = None

    def compose(self):
        """Yields the labels list view."""
        yield self.label_list

    def action_shrink_labels(self) -> None:
        """Decreases labels pane width."""
        if self.styles.width is not None:
            current_width = int(self.styles.width.value)
            self.styles.width = max(15, current_width - 2)

    def action_expand_labels(self) -> None:
        """Increases labels pane width."""
        if self.styles.width is not None:
            current_width = int(self.styles.width.value)
            self.styles.width = min(60, current_width + 2)

    def action_cursor_up(self) -> None:
        """Moves the selection cursor up."""
        self.label_list.action_cursor_up()
        self._refresh_footer_shortcuts()

    def action_cursor_down(self) -> None:
        """Moves the selection cursor down."""
        self.label_list.action_cursor_down()
        self._refresh_footer_shortcuts()

    def action_first_label(self) -> None:
        """Jumps to the first label."""
        if len(self.label_list) > 0:
            self.label_list.index = 0
            self._refresh_footer_shortcuts()

    def action_last_label(self) -> None:
        """Jumps to the last label."""
        if len(self.label_list) > 0:
            self.label_list.index = len(self.label_list) - 1
            self._refresh_footer_shortcuts()

    def on_mount(self):
        """Populates labels from the database on mount."""
        self.refresh_labels()

    def refresh_labels(self, selected_label_id: str | None = None) -> None:
        """Reload label rows while preserving current selected label."""
        selected_label_id = (
            self._get_selected_label_id()
            if selected_label_id is None
            else selected_label_id
        )
        self.run_worker(
            lambda: self._load_labels_worker(selected_label_id),
            thread=True,
            exclusive=True,
        )

    def _get_selected_label_id(self) -> str | None:
        """Return selected label identifier from current list state."""
        if self._active_label_id:
            return self._active_label_id
        for child in self.label_list.children:
            if isinstance(child, LabelItem) and child.has_class("selected"):
                return child.label_id
        index = self.label_list.index
        if index is not None and 0 <= index < len(self.label_list.children):
            item = self.label_list.children[index]
            if isinstance(item, LabelItem):
                return item.label_id
        return None

    def _get_cursor_label_id(self) -> str | None:
        """Return the label identifier under the current sidebar cursor."""
        index = self.label_list.index
        if index is None or not (0 <= index < len(self.label_list.children)):
            return None
        item = self.label_list.children[index]
        if isinstance(item, LabelItem):
            return item.label_id
        return None

    def _current_cursor_label_is_editable(self) -> bool:
        """Return True when the highlighted label can be edited."""
        if not self.is_attached:
            return False
        label_id = self._get_cursor_label_id() or self._get_selected_label_id()
        if not label_id:
            return False
        return self.shmail_app.label_state.can_edit_label(label_id)

    def _load_labels_worker(self, selected_label_id: str | None) -> None:
        """Loads labels in a worker thread and mounts results on UI thread."""
        labels = self.shmail_app.label_state.refresh()
        self.app.call_from_thread(self._populate_labels, labels, selected_label_id)

    def apply_label_patch(self, label: dict) -> None:
        """Apply one targeted label-state patch without rebuilding the full list."""
        label_id = str(label.get("id") or "")
        unread_count = int(label.get("unread_count") or 0)
        full_name = str(label.get("name") or "")
        display_name = full_name.split("/")[-1] if full_name else ""
        background_color = str(label.get("background_color") or "") or None
        for child in self.label_list.children:
            if not isinstance(child, LabelItem):
                continue
            if str(child.label_id) != label_id:
                continue
            child.display_name = display_name or child.display_name
            child.background_color = background_color
            child.set_count(unread_count)
            try:
                name_widget = child.query_one(".label-name", Static)
                name_widget.update(child._compose_label_text())
                color_widget = child.query_one(".label-color-chip", Static)
                color_widget.update("■" if background_color else " ")
                color_widget.styles.color = background_color or "transparent"
            except Exception:
                pass
            return
        self.refresh_labels()

    def _populate_labels(
        self, labels: list[dict], selected_label_id: str | None
    ) -> None:
        """Constructs the flattened list hierarchy from fetched label rows."""
        self.label_list.clear()

        main_map = {
            "INBOX": "Inbox",
            "STARRED": "Starred",
            "SENT": "Sent",
            "DRAFT": "Drafts",
            "OUTBOX": "Outbox",
        }
        cat_map = {
            "CATEGORY_PERSONAL": "Personal",
            "CATEGORY_SOCIAL": "Social",
            "CATEGORY_UPDATES": "Updates",
            "CATEGORY_FORUMS": "Forums",
            "CATEGORY_PROMOTIONS": "Promotions",
        }
        more_map = {
            "IMPORTANT": "Important",
            "SPAM": "Spam",
            "TRASH": "Bin",
            "CHAT": "Chat",
            "ALL": "All Mail",
        }

        found_main = {}
        found_cats = {}
        found_more = {}
        user_labels = []

        for label in labels:
            name = label["name"].upper()
            label_id = label["id"].upper()

            if name in main_map or label_id in main_map:
                match_key = name if name in main_map else label_id
                found_main[match_key] = label
            elif name in cat_map or label_id in cat_map:
                match_key = name if name in cat_map else label_id
                found_cats[match_key] = label
            elif name in more_map or label_id in more_map:
                match_key = name if name in more_map else label_id
                found_more[match_key] = label
            elif label["type"] == "user":
                user_labels.append(label)
            else:
                found_more[name] = label

        inbox_index = -1
        selected_index = -1
        for key, disp in main_map.items():
            if key in found_main:
                label_info = found_main[key]
                self.label_list.append(
                    LabelItem(
                        disp,
                        label_info["id"],
                        label_info["unread_count"],
                        depth=1,
                        background_color=label_info.get("background_color"),
                    )
                )
                if selected_label_id and label_info["id"] == selected_label_id:
                    selected_index = len(self.label_list) - 1
                if key == "INBOX":
                    inbox_index = len(self.label_list) - 1

        if found_cats:
            self.label_list.append(LabelHeader("Categories"))
            for key, disp in cat_map.items():
                if key in found_cats:
                    label_info = found_cats[key]
                    self.label_list.append(
                        LabelItem(
                            disp,
                            label_info["id"],
                            label_info["unread_count"],
                            depth=1,
                            background_color=label_info.get("background_color"),
                        )
                    )
                    if selected_label_id and label_info["id"] == selected_label_id:
                        selected_index = len(self.label_list) - 1

        if found_more:
            self.label_list.append(LabelHeader("More"))
            for key, disp in more_map.items():
                if key in found_more:
                    label_info = found_more[key]
                    self.label_list.append(
                        LabelItem(
                            disp,
                            label_info["id"],
                            label_info["unread_count"],
                            depth=1,
                            background_color=label_info.get("background_color"),
                        )
                    )
                    if selected_label_id and label_info["id"] == selected_label_id:
                        selected_index = len(self.label_list) - 1

        if user_labels:
            self.label_list.append(LabelHeader("Labels"))
            sorted_labels = sorted(user_labels, key=lambda x: x["name"])
            for i, label in enumerate(sorted_labels):
                parts = label["name"].split("/")
                depth = len(parts)
                display_name = parts[-1]

                is_last = True
                if i < len(sorted_labels) - 1:
                    next_label = sorted_labels[i + 1]
                    next_parts = next_label["name"].split("/")
                    if len(next_parts) >= depth:
                        if "/".join(next_parts[: depth - 1]) == "/".join(
                            parts[: depth - 1]
                        ):
                            is_last = False

                self.label_list.append(
                    LabelItem(
                        display_name,
                        label["id"],
                        label["unread_count"],
                        depth=depth,
                        is_last_child=is_last,
                        background_color=label.get("background_color"),
                    )
                )
                if selected_label_id and label["id"] == selected_label_id:
                    selected_index = len(self.label_list) - 1

        target_index = selected_index if selected_index >= 0 else inbox_index
        if target_index >= 0:
            self.label_list.index = target_index
            item = self.label_list.children[target_index]
            if isinstance(item, LabelItem):
                self._set_active_label(item.label_id)
                self.post_message(self.LabelSelected(item.label_id))
        self._refresh_footer_shortcuts()

    def on_list_view_selected(self, event: ListView.Selected):
        """Handles label selection and manages persistent visual state."""
        if isinstance(event.item, LabelItem):
            self._set_active_label(event.item.label_id)
            self.post_message(self.LabelSelected(event.item.label_id))
            self._refresh_footer_shortcuts()

    def on_list_view_highlighted(self, _event: ListView.Highlighted) -> None:
        """Refresh footer shortcuts when the highlighted row changes."""
        self._refresh_footer_shortcuts()

    def action_new_label(self) -> None:
        """Open the create-label modal from the labels pane."""
        self.app.push_screen(
            LabelEditScreen(LabelEditorSeed()), self._on_label_editor_closed
        )

    def action_edit_label(self) -> None:
        """Open the edit-label modal for the selected custom label."""
        selected_label_id = self._get_cursor_label_id() or self._get_selected_label_id()
        if not selected_label_id:
            return
        label_state = self.shmail_app.label_state
        if not label_state.can_edit_label(selected_label_id):
            notify = getattr(self.app, "notify", None)
            if callable(notify):
                notify("System labels cannot be modified.", severity="warning")
            return
        self.app.push_screen(
            LabelEditScreen(LabelEditorSeed(label_id=selected_label_id)),
            self._on_label_editor_closed,
        )

    def _on_label_editor_closed(self, result: LabelMutationResult | None) -> None:
        """Refresh the sidebar after one label-management mutation."""
        if result is None:
            return
        self.refresh_labels(selected_label_id=result.focus_label_id)

    def on_descendant_focus(self, _event) -> None:
        """Sync cursor position to the active label when sidebar regains focus."""
        self._sync_cursor_to_active_label()

    def _set_active_label(self, label_id: str) -> None:
        """Mark one label as active and clear stale active styling."""
        self._active_label_id = label_id
        for child in self.label_list.query(LabelItem):
            if child.label_id == label_id:
                child.add_class("selected")
            else:
                child.remove_class("selected")

    def _sync_cursor_to_active_label(self) -> None:
        """Move the sidebar cursor onto the active label when possible."""
        if not self._active_label_id:
            return
        for index, child in enumerate(self.label_list.children):
            if isinstance(child, LabelItem) and child.label_id == self._active_label_id:
                self.label_list.index = index
                self._refresh_footer_shortcuts()
                return

    def _refresh_footer_shortcuts(self) -> None:
        """Ask the current screen to rebuild footer shortcuts when available."""
        refresh = getattr(self.screen, "refresh_footer_shortcuts", None)
        if callable(refresh):
            refresh()
