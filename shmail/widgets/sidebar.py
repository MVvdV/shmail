from typing import TYPE_CHECKING, cast

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static, Tree

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class Sidebar(Vertical):
    """A widget to display and navigate Gmail labels."""

    @property
    def shmail_app(self) -> ShmailApp:
        return cast("ShmailApp", self.app)

    class LabelSelected(Message):
        """Sent when a label is selected in the tree."""

        def __init__(self, label_id: str) -> None:
            self.label_id = label_id
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Hidden root to show labels as a flat/nested list
        self.label_tree = Tree("Labels")
        self.label_tree.show_root = False

    def compose(self):
        """Yield the components of the sidebar."""
        yield Static("SHMAIL", id="sidebar-header")
        yield self.label_tree

    def on_mount(self):
        """Initial population of labels."""
        self._load_labels()

    def _load_labels(self):
        """Fetch labels from the database and populate the Tree."""
        labels = self.shmail_app.db.get_labels()

        self.label_tree.clear()
        for label in labels:
            # Store label_id in 'data' for later retrieval
            self.label_tree.root.add(label["name"], data=label["id"])

        self.label_tree.root.expand()

    def on_tree_node_selected(self, event: Tree.NodeSelected):
        """Handle selection of a label and notify the parent."""
        label_id = event.node.data
        if isinstance(label_id, str):
            self.post_message(self.LabelSelected(label_id))
