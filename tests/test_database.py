from dataclasses import replace

import pytest
from django.core.exceptions import ImproperlyConfigured

from app.config import Settings
from app.database import database_config


@pytest.fixture
def config():
    return Settings()


def test_database_url_chooses_postgres_with_tls_and_short_lived_connections(config, monkeypatch):
    monkeypatch.delenv("DATABASE_SSL_ROOT_CERT", raising=False)
    database = database_config(replace(config, database_url="postgres://app:s3cret@db.example:1234/treinamentos?sslmode=require"))
    assert database["ENGINE"] == "django.db.backends.postgresql"
    assert database["NAME"] == "treinamentos"
    assert database["CONN_MAX_AGE"] == 0
    assert database["OPTIONS"]["sslmode"] == "require"
    assert database["OPTIONS"]["connect_timeout"] == 10


def test_ca_certificate_enables_hostname_verification(config, monkeypatch):
    monkeypatch.setenv("DATABASE_SSL_ROOT_CERT", "/etc/secrets/aiven-ca.pem")
    database = database_config(replace(config, database_url="postgres://app:pw@db.example/db"))
    assert database["OPTIONS"]["sslmode"] == "verify-full"
    assert database["OPTIONS"]["sslrootcert"] == "/etc/secrets/aiven-ca.pem"


@pytest.mark.parametrize("uri", [
    "postgres://\nCLICK_TO:REVEAL_PASSWORD\n@host:27949/defaultdb?sslmode=require",
    "mysql://user:secret@host/db", "postgres://user@host/db", "postgres://user:secret@host/",
    "postgres://user:secret@host/db?sslmode=disable", "postgres://user:secret@host:bad/db",
])
def test_invalid_database_urls_fail_without_exposing_password(config, uri):
    with pytest.raises(ImproperlyConfigured) as exc:
        database_config(replace(config, database_url=uri))
    assert "secret" not in str(exc.value)
    assert "CLICK_TO" not in str(exc.value)


def test_local_postgres_can_disable_tls_and_uri_is_not_represented(config, monkeypatch):
    monkeypatch.delenv("DATABASE_SSL_ROOT_CERT", raising=False)
    config = replace(config, database_url="postgres://user:secret@127.0.0.1:5432/db?sslmode=disable")
    assert database_config(config)["OPTIONS"]["sslmode"] == "disable"
    assert "secret" not in repr(config)


def test_missing_url_requires_postgres_config(config):
    with pytest.raises(ImproperlyConfigured, match="DATABASE_URL"):
        database_config(config)
