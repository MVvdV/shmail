import logging
import pytest
from unittest.mock import MagicMock, patch
from shmail.services.auth import AuthService
from shmail.services.db import DatabaseService


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh, isolated database for each test."""
    db_path = tmp_path / "test_standards.db"
    db_service = DatabaseService(db_path=db_path)
    db_service.initialize()
    return db_service


def test_auth_service_logging_on_failure(caplog):
    """Verify that AuthService logs an exception when discovery fails."""
    # We set the level to ERROR to ensure we catch the exception log
    with caplog.at_level(logging.ERROR):
        auth = AuthService()

        # Mock the engine to raise an exception
        with patch.object(
            AuthService, "_run_oauth_flow", side_effect=Exception("OAuth Crash")
        ):
            with pytest.raises(Exception):
                auth.discover_and_authenticate()

        # Assert the standard error message is present in the logs
        assert "Discovery authentication failed" in caplog.text
        assert "OAuth Crash" in caplog.text


def test_db_service_transaction_logging(test_db, caplog):
    """Verify that DatabaseService logs failures during transactions."""
    with caplog.at_level(logging.ERROR):
        # We try to perform an operation that will fail inside a transaction
        # e.g., inserting a duplicate primary key if we didn't have IGNORE,
        # or just raising a manual error.

        with pytest.raises(RuntimeError):
            with test_db.transaction() as conn:
                raise RuntimeError("Simulated DB Failure")

        # Assert the standard diagnostic message is present
        assert "Database transaction failed" in caplog.text
        assert "Simulated DB Failure" in caplog.text


def test_gmail_service_logging_on_api_error(caplog):
    """Verify that GmailService logs technical details on API failures."""
    from shmail.services.gmail import GmailService

    with caplog.at_level(logging.ERROR):
        # We don't need real credentials for this mock test
        service = GmailService(MagicMock())

        # Mock the users() call to fail
        with patch.object(service.service, "users", side_effect=Exception("API Down")):
            with pytest.raises(Exception):
                service.get_profile()

        assert "Failed to fetch user profile" in caplog.text
        assert "API Down" in caplog.text
