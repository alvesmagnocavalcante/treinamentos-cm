import importlib
import importlib.util

import pytest


def test_real_crew_preserves_agents_model_and_human_gate(monkeypatch, tmp_path):
    if importlib.util.find_spec("crewai") is None:
        pytest.skip("Instale requirements.txt para validar a estrutura real do CrewAI.")
    import appdirs
    from crewai_core.token_manager import TokenManager

    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("CREWAI_TRACING_ENABLED", "false")
    monkeypatch.setenv("CREWAI_TELEMETRY_DISABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    monkeypatch.setenv("CREWAI_MODEL", "")
    monkeypatch.setattr(appdirs, "user_data_dir", lambda *a, **kw: str(tmp_path))
    monkeypatch.setattr(TokenManager, "_get_secure_storage_path", staticmethod(lambda: tmp_path))
    module = importlib.import_module("pipeline.crew")
    crew = module.build_crew("Procedimento fictício para teste estrutural.")
    assert len(crew.agents) == 2
    assert len(crew.tasks) == 2
    assert crew.tasks[-1].human_input is True
    assert crew.agents[0].llm.model == "openrouter/free"
    assert crew.tasks[-1].context == [crew.tasks[0]]
