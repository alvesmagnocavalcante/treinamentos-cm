import json
from unittest.mock import MagicMock

import pytest

from app.services.drive import DriveClient, SCOPE
from app.services.errors import ServiceError


@pytest.mark.parametrize("value", ["{invalid", "[]", "{}", '{"private_key":"sensitive-invalid-value"}'])
def test_invalid_environment_credentials_do_not_expose_secrets(value, monkeypatch, settings):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", value)
    with pytest.raises(ServiceError) as error:
        with DriveClient.connect(settings.SERVICE_SETTINGS):
            pytest.fail("Invalid credentials accepted")
    assert error.value.status_code == 503
    assert value not in str(error.value)
    assert "sensitive-invalid-value" not in str(error.value)


def test_environment_credentials_take_precedence_over_adc(monkeypatch, settings):
    payload = {"type": "service_account", "client_email": "test@example.test"}
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps(payload))
    create = MagicMock()
    session = MagicMock()
    adc = MagicMock(side_effect=AssertionError("ADC should not be used"))
    monkeypatch.setattr("app.services.drive.Credentials.from_service_account_info", create)
    monkeypatch.setattr("app.services.drive.AuthorizedSession", session)
    monkeypatch.setattr("google.auth.default", adc)
    with DriveClient.connect(settings.SERVICE_SETTINGS) as drive:
        assert drive.session is session.return_value.__enter__.return_value
    create.assert_called_once_with(payload, scopes=[SCOPE])
    session.assert_called_once_with(create.return_value, refresh_timeout=settings.SERVICE_SETTINGS.timeout_seconds)
