import pytest

from app.config import Settings


@pytest.mark.parametrize("value, expected", [
    ("openrouter/free", "openrouter/free"), ("openrouter/auto", "openrouter/auto"),
    ("anthropic/example", "anthropic/example"),
])
def test_openrouter_model_ids(monkeypatch, value, expected):
    monkeypatch.setenv("OPENROUTER_MODEL", value)
    assert Settings.from_env().openrouter_model == expected


def test_settings_do_not_repr_keys():
    settings = Settings(google_api_key="google-secret", openrouter_api_key="router-secret")
    assert "secret" not in repr(settings)
    with pytest.raises(ValueError):
        Settings(overlap_tokens=1000)
