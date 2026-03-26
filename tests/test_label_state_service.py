import pytest

from shmail.services.db import DatabaseRepository
from shmail.services.label_query import LabelQueryService
from shmail.services.label_state import LabelStateService


@pytest.fixture
def test_db(tmp_path):
    """Provide a temporary database for label-state tests."""
    db_file = tmp_path / "label_state.db"
    repository = DatabaseRepository(db_path=db_file)
    repository.initialize()
    return repository


def _build_label_state(test_db: DatabaseRepository) -> LabelStateService:
    """Create a label-state service backed by the temporary repository."""
    return LabelStateService(LabelQueryService(test_db))


class FakeGmailService:
    """Minimal Gmail stub for label-state mutation tests."""

    def __init__(self) -> None:
        self.patches: list[tuple[str, dict]] = []

    def patch_label(self, label_id: str, body: dict) -> dict:
        self.patches.append((label_id, body))
        response = {"id": label_id, "name": body["name"], "type": "user"}
        if body.get("color") is not None:
            response["color"] = body["color"]
        return response


def test_parent_candidates_exclude_self_and_descendants(test_db):
    """Ensure edit-parent options cannot create circular nesting."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "work", "Work", "user")
        test_db.upsert_label(conn, "client", "Work/Client", "user")
        test_db.upsert_label(conn, "urgent", "Work/Client/Urgent", "user")
        test_db.upsert_label(conn, "personal", "Personal", "user")

    label_state = _build_label_state(test_db)
    parent_ids = {
        str(label["id"]) for label in label_state.list_parent_candidates("client")
    }

    assert "client" not in parent_ids
    assert "urgent" not in parent_ids
    assert "work" in parent_ids
    assert "personal" in parent_ids


def test_create_label_stores_nested_name_and_color_metadata(test_db):
    """Ensure new labels use slash nesting and persist chosen Gmail colors."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "projects", "Projects", "user")

    label_state = _build_label_state(test_db)
    result = label_state.create_label(
        leaf_name="Shmail",
        parent_label_id="projects",
        background_color="#4986E7",
        text_color="#FFFFFF",
    )

    created = test_db.get_label(result.label_id or "")
    assert created is not None
    assert created["name"] == "Projects/Shmail"
    assert created["background_color"] == "#4986E7"
    assert created["text_color"] == "#FFFFFF"


def test_update_label_renames_descendants_with_parent_move(test_db):
    """Ensure moving a parent label keeps child slash paths coherent."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "work", "Work", "user")
        test_db.upsert_label(conn, "client", "Work/Client", "user")
        test_db.upsert_label(conn, "urgent", "Work/Client/Urgent", "user")
        test_db.upsert_label(conn, "archive", "Archive", "user")

    label_state = _build_label_state(test_db)
    label_state.update_label(
        label_id="client",
        leaf_name="Active",
        parent_label_id="archive",
        background_color="#16A765",
        text_color="#FFFFFF",
    )

    updated = test_db.get_label("client")
    descendant = test_db.get_label("urgent")
    assert updated is not None
    assert descendant is not None
    assert updated["name"] == "Archive/Active"
    assert updated["background_color"] == "#16A765"
    assert descendant["name"] == "Archive/Active/Urgent"


def test_delete_label_blocks_when_sublabels_exist(test_db):
    """Ensure delete refuses parent labels until descendants are removed."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "work", "Work", "user")
        test_db.upsert_label(conn, "client", "Work/Client", "user")

    label_state = _build_label_state(test_db)

    with pytest.raises(ValueError, match="Delete sublabels first"):
        label_state.delete_label(label_id="work")


def test_system_label_cannot_be_modified(test_db):
    """Ensure user-only mutations reject Gmail system labels."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "system")

    label_state = _build_label_state(test_db)

    with pytest.raises(ValueError, match="System labels"):
        label_state.update_label(
            label_id="INBOX",
            leaf_name="Renamed",
            parent_label_id=None,
            background_color=None,
            text_color=None,
        )


def test_update_label_clears_local_colors_when_provider_clears_them(test_db):
    """Ensure clearing a color does not leave stale local color metadata."""
    with test_db.transaction() as conn:
        test_db.upsert_label(
            conn,
            "project",
            "Project",
            "user",
            background_color="#4986E7",
            text_color="#FFFFFF",
        )

    label_state = _build_label_state(test_db)
    gmail = FakeGmailService()

    label_state.update_label(
        label_id="project",
        leaf_name="Project",
        parent_label_id=None,
        background_color=None,
        text_color=None,
        gmail_service=gmail,
    )

    stored = test_db.get_label("project")
    assert stored is not None
    assert stored["background_color"] is None
    assert stored["text_color"] is None
    assert gmail.patches == [("project", {"name": "Project", "color": None})]
