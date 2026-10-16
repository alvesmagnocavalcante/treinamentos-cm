import httpx
import pytest
import requests

from app.config import Settings


@pytest.fixture(autouse=True)
def prevent_paid_http_calls(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Rede externa bloqueada nos testes; utilize httpx.MockTransport.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)


@pytest.fixture
def platform_settings(settings, monkeypatch):
    from app import runtime
    from app.services.vector_store import VectorStore

    config = Settings()
    settings.SERVICE_SETTINGS = config
    monkeypatch.setattr(runtime, "store", VectorStore(config))
    return config


@pytest.fixture
def staff_client(client, django_user_model):
    user = django_user_model.objects.create(username="gestor", is_staff=True, is_superuser=True)
    user.set_unusable_password()
    user.save()
    client.force_login(user)
    return client


@pytest.fixture
def employee_client(client, django_user_model):
    user = django_user_model.objects.create(username="colaborador")
    user.set_unusable_password()
    user.save()
    client.force_login(user)
    return client
