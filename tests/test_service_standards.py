import logging
import pytest
from unittest.mock import MagicMock, patch
from shmail.services.auth import AuthService
from shmail.services.db import DatabaseRepository


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh, isolated database for each test."""
    db_path = tmp_path / "test_standards.db"
    repository = DatabaseRepository(db_path=db_path)
    repository.initialize()
    return repository


def test_auth_service_logging_on_failure(caplog):
    """Verify that AuthService logs an exception when discovery fails."""
    with caplog.at_level(logging.ERROR):
        auth = AuthService()

        with patch.object(
            AuthService, "_run_oauth_flow", side_effect=Exception("OAuth Crash")
        ):
            with pytest.raises(Exception):
                auth.discover_and_authenticate()

        assert "Discovery authentication failed" in caplog.text
        assert "OAuth Crash" in caplog.text


def test_repository_transaction_logging(test_db, caplog):
    """Verify that DatabaseRepository logs failures during transactions."""
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            with test_db.transaction():
                raise RuntimeError("Simulated DB Failure")

        assert "Database transaction failed" in caplog.text
        assert "Simulated DB Failure" in caplog.text


def test_gmail_service_logging_on_api_error(caplog):
    """Verify that GmailService logs technical details on API failures."""
    from shmail.services.gmail import GmailService

    with caplog.at_level(logging.ERROR):
        service = GmailService(MagicMock())

        with patch.object(service.service, "users", side_effect=Exception("API Down")):
            with pytest.raises(Exception):
                service.get_profile()

        assert "Failed to fetch user profile" in caplog.text
        assert "API Down" in caplog.text
