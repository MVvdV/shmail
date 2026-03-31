"""Inspector screen for pending and failed local mutation replay items."""

from __future__ import annotations

import json
from typing import Any, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from shmail.config import settings
from shmail.widgets.shortcuts import binding_choices_label, movement_pair_label


class MutationListItem(ListItem):
    """List row representing one mutation log record."""

    def __init__(self, mutation: dict) -> None:
        super().__init__()
        self.add_class("mutation-inspector-item")
        self.mutation = mutation
        state = str(mutation.get("state") or "")
        if state == "failed":
            self.add_class("-failed")
        elif state == "blocked":
            self.add_class("-blocked")

    def compose(self) -> ComposeResult:
        state = str(self.mutation.get("state") or "")
        action = str(self.mutation.get("action_type") or "")
        target = str(self.mutation.get("target_kind") or "")
        label = f"{state:<13} {action} [{target}]"
        yield Static(label, classes="mutation-inspector-row", markup=False)


class MutationInspectorScreen(ModalScreen[None]):
    """Review queued mutations and manually trigger deferred replay actions."""

    BINDINGS = [
        Binding(settings.keybindings.close, "close", "Close", show=False),
        Binding(settings.keybindings.up, "cursor_up", "Previous", show=False),
        Binding(settings.keybindings.down, "cursor_down", "Next", show=False),
        Binding("r", "retry_selected", "Retry", show=False),
        Binding("ctrl+r", "replay_all", "Replay All", show=False),
        Binding("b", "block_selected", "Block", show=False),
        Binding("f", "refresh", "Refresh", show=False),
    ]

    def __init__(self) -> None:
        super().__init__(id="mutation-inspector-screen")

    def compose(self) -> ComposeResult:
        with Vertical(id="mutation-inspector-modal"):
            yield Static("Mutation Inspector", id="mutation-inspector-title")
            yield Static(
                "Review pending, failed, and blocked local replay items.",
                id="mutation-inspector-body",
                markup=False,
            )
            with Horizontal(id="mutation-inspector-content"):
                yield ListView(id="mutation-inspector-list")
                with Vertical(id="mutation-inspector-detail"):
                    yield Static(id="mutation-inspector-detail-title")
                    yield Static(id="mutation-inspector-detail-meta", markup=False)
                    yield Static(id="mutation-inspector-detail-payload", markup=False)
            with Horizontal(id="mutation-inspector-shortcuts"):
                yield Static("R", classes="shortcut-key")
                yield Static("Retry", classes="shortcut-label")
                yield Static("•", classes="shortcut-separator")
                yield Static("Ctrl+R", classes="shortcut-key")
                yield Static("Replay All", classes="shortcut-label")
                yield Static("•", classes="shortcut-separator")
                yield Static("B", classes="shortcut-key")
                yield Static("Block", classes="shortcut-label")
                yield Static("•", classes="shortcut-separator")
                yield Static(
                    movement_pair_label(
                        settings.keybindings.up, settings.keybindings.down
                    ),
                    classes="shortcut-key",
                    markup=False,
                )
                yield Static("Move", classes="shortcut-label")
                yield Static("•", classes="shortcut-separator")
                yield Static(
                    binding_choices_label(settings.keybindings.close, "Q/ESC"),
                    classes="shortcut-key",
                    markup=False,
                )
                yield Static("Close", classes="shortcut-label")

    def on_mount(self) -> None:
        self.action_refresh()

    def action_refresh(self) -> None:
        """Reload the mutation list and detail pane."""
        app = cast(Any, self.app)
        items = []
        for row in app.repository.list_mutations(limit=250):
            items.append(MutationListItem(row))
        list_view = self.query_one("#mutation-inspector-list", ListView)
        list_view.clear()
        for item in items:
            list_view.append(item)
        if items:
            list_view.index = 0
            self._render_detail(items[0].mutation)
            list_view.focus()
        else:
            self._render_empty_detail()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Render detail for the highlighted mutation row."""
        if isinstance(event.item, MutationListItem):
            self._render_detail(event.item.mutation)

    def action_cursor_up(self) -> None:
        """Move inspector selection upward."""
        self.query_one("#mutation-inspector-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move inspector selection downward."""
        self.query_one("#mutation-inspector-list", ListView).action_cursor_down()

    def action_retry_selected(self) -> None:
        """Mark the selected mutation ready and attempt replay once."""
        row = self._selected_mutation()
        if row is None:
            return
        app = cast(Any, self.app)
        app.mutation_log.mark_ready(str(row.get("id") or ""))
        app.replay_mutations([str(row.get("id") or "")])
        self.action_refresh()

    def action_replay_all(self) -> None:
        """Attempt replay across all currently replayable mutations."""
        cast(Any, self.app).replay_mutations(None)
        self.action_refresh()

    def action_block_selected(self) -> None:
        """Move the selected mutation into blocked state."""
        row = self._selected_mutation()
        if row is None:
            return
        app = cast(Any, self.app)
        app.mutation_log.mark_blocked(
            str(row.get("id") or ""), "Blocked manually from the mutation inspector."
        )
        app.refresh_mutation_views()
        self.action_refresh()

    def action_close(self) -> None:
        """Dismiss the inspector modal."""
        self.dismiss(None)

    def _selected_mutation(self) -> dict | None:
        """Return the currently highlighted mutation row payload."""
        list_view = self.query_one("#mutation-inspector-list", ListView)
        if list_view.index is None or list_view.index < 0:
            return None
        item = list_view.highlighted_child
        if isinstance(item, MutationListItem):
            return item.mutation
        return None

    def _render_detail(self, mutation: dict) -> None:
        """Render details for one selected mutation."""
        self.query_one("#mutation-inspector-detail-title", Static).update(
            str(mutation.get("action_type") or "Mutation")
        )
        meta = (
            f"State: {mutation.get('state') or 'unknown'}\n"
            f"Provider: {mutation.get('provider_key') or 'unknown'}\n"
            f"Target: {mutation.get('target_kind') or 'unknown'} {mutation.get('target_id') or ''}\n"
            f"Updated: {mutation.get('updated_at') or ''}"
        )
        self.query_one("#mutation-inspector-detail-meta", Static).update(meta)
        payload_json = str(mutation.get("payload_json") or "{}")
        try:
            payload = json.dumps(json.loads(payload_json), indent=2, sort_keys=True)
        except Exception:
            payload = payload_json
        error_message = str(mutation.get("error_message") or "").strip()
        detail = (
            payload if not error_message else f"Error: {error_message}\n\n{payload}"
        )
        self.query_one("#mutation-inspector-detail-payload", Static).update(detail)

    def _render_empty_detail(self) -> None:
        """Render the empty inspector state."""
        self.query_one("#mutation-inspector-detail-title", Static).update(
            "No mutations"
        )
        self.query_one("#mutation-inspector-detail-meta", Static).update(
            "No queued, failed, or blocked mutations to review."
        )
        self.query_one("#mutation-inspector-detail-payload", Static).update("")
