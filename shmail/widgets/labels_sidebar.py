from typing import TYPE_CHECKING, cast

from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

from shmail.config import settings

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class LabelHeader(ListItem):
    """A non-selectable section divider with a labeled top border."""

    def __init__(self, title: str):
        super().__init__(disabled=True)
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
    ):
        super().__init__()
        self.display_name = display_name
        self.label_id = label_id
        self.count = count
        self.depth = depth
        self.is_last_child = is_last_child

    def compose(self):
        """Constructs the label text with hierarchical connectors."""
        if self.depth <= 1:
            indent = "  " * self.depth
            connector = ""
        else:
            indent = "  " * (self.depth - 1)
            connector = "└ " if self.is_last_child else "├ "

        if self.count > 0:
            self.add_class("unread")

        label_text = f"{indent}{connector}{self.display_name}"
        yield Static(label_text, classes="label-name", markup=False)

        count_text = f"({self.count})" if self.count > 0 else ""
        yield Static(count_text, classes="label-count", markup=False)

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


class LabelsSidebar(Vertical):
    """A navigation pane for Gmail labels organized by category and hierarchy."""

    can_focus = False

    BINDINGS = [
        Binding("[", "shrink_labels", "Shrink Labels", show=False),
        Binding("]", "expand_labels", "Expand Labels", show=False),
        Binding(settings.keybindings.up, "cursor_up", "Previous Label", show=False),
        Binding(settings.keybindings.down, "cursor_down", "Next Label", show=False),
        Binding("g", "first_label", "First Label", show=False),
        Binding("G", "last_label", "Last Label", show=False),
    ]

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Returns the active shortcuts for the Labels pane."""
        return [
            ("ENTER", "Select"),
            ("C", "Compose"),
            ("J/K", "Move"),
            ("G/g", "Top/End"),
            ("TAB", "Threads"),
            ("[/]", "Resize"),
        ]

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

    def action_cursor_down(self) -> None:
        """Moves the selection cursor down."""
        self.label_list.action_cursor_down()

    def action_first_label(self) -> None:
        """Jumps to the first label."""
        if len(self.label_list) > 0:
            self.label_list.index = 0

    def action_last_label(self) -> None:
        """Jumps to the last label."""
        if len(self.label_list) > 0:
            self.label_list.index = len(self.label_list) - 1

    def on_mount(self):
        """Populates labels from the database on mount."""
        self.refresh_labels()
        if hasattr(type(self.shmail_app), "drafts_revision"):
            self.watch(self.shmail_app, "drafts_revision", self._on_drafts_revision)

    def _on_drafts_revision(self, _revision: int) -> None:
        """Refresh label counts after local draft state changes."""
        self.refresh_labels()

    def refresh_labels(self) -> None:
        """Reload label rows while preserving current selected label."""
        selected_label_id = self._get_selected_label_id()
        self.run_worker(
            lambda: self._load_labels_worker(selected_label_id),
            thread=True,
            exclusive=True,
        )

    def _get_selected_label_id(self) -> str | None:
        """Return selected label identifier from current list state."""
        for child in self.label_list.children:
            if isinstance(child, LabelItem) and child.has_class("selected"):
                return child.label_id
        index = self.label_list.index
        if index is not None and 0 <= index < len(self.label_list.children):
            item = self.label_list.children[index]
            if isinstance(item, LabelItem):
                return item.label_id
        return None

    def update_draft_count(self, count: int) -> None:
        """Update DRAFT label count without reloading all labels."""
        for child in self.label_list.children:
            if not isinstance(child, LabelItem):
                continue
            label_id = str(child.label_id).upper()
            label_name = str(child.display_name).upper()
            if label_id == "DRAFT" or label_name.startswith("DRAFT"):
                child.set_count(count)
                return
        self.refresh_labels()

    def _load_labels_worker(self, selected_label_id: str | None) -> None:
        """Loads labels in a worker thread and mounts results on UI thread."""
        labels = self.shmail_app.db.get_labels_with_counts()
        self.app.call_from_thread(self._populate_labels, labels, selected_label_id)

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
        }
        cat_map = {
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
                        disp, label_info["id"], label_info["unread_count"], depth=1
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
                            disp, label_info["id"], label_info["unread_count"], depth=1
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
                            disp, label_info["id"], label_info["unread_count"], depth=1
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
                    )
                )
                if selected_label_id and label["id"] == selected_label_id:
                    selected_index = len(self.label_list) - 1

        target_index = selected_index if selected_index >= 0 else inbox_index
        if target_index >= 0:
            self.label_list.index = target_index
            self.label_list.focus()
            item = self.label_list.children[target_index]
            if isinstance(item, LabelItem):
                item.add_class("selected")
                self.post_message(self.LabelSelected(item.label_id))

    def on_list_view_selected(self, event: ListView.Selected):
        """Handles label selection and manages persistent visual state."""
        if isinstance(event.item, LabelItem):
            for child in self.label_list.query(LabelItem):
                child.remove_class("selected")

            event.item.add_class("selected")
            self.post_message(self.LabelSelected(event.item.label_id))
