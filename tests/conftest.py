import httpx
import pytest


@pytest.fixture(autouse=True)
def prevent_paid_http_calls(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Rede externa bloqueada nos testes; utilize httpx.MockTransport.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
