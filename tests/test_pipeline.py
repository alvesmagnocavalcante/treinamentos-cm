import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


def test_script_pipeline_saves_result_without_video(monkeypatch, tmp_path):
    crew_module = ModuleType("pipeline.crew")
    ingest_module = ModuleType("pipeline.ingest")
    result = "CENA 1\nNarração: Consulte a disponibilidade."
    kickoff = Mock(return_value=result)
    crew_module.build_crew = Mock(return_value=SimpleNamespace(
        tasks=[SimpleNamespace(output="1. Consulte a disponibilidade.")], kickoff=kickoff,
    ))
    ingest_module.pop_to_markdown = Mock(return_value="Procedimento de teste")
    monkeypatch.setitem(sys.modules, "pipeline.crew", crew_module)
    monkeypatch.setitem(sys.modules, "pipeline.ingest", ingest_module)
    monkeypatch.delitem(sys.modules, "pipeline.run", raising=False)
    run = importlib.import_module("pipeline.run")
    monkeypatch.setattr(run, "__file__", str(tmp_path / "pipeline" / "run.py"))
    monkeypatch.setattr(sys, "argv", ["pipeline.run", "--pop", "test.docx"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    try:
        run.main()
        kickoff.assert_called_once_with(inputs={"pop_markdown": "Procedimento de teste"})
        saved = list((tmp_path / "testdata").glob("roteiro-aprovado-*.md"))
        assert len(saved) == 1
        assert saved[0].read_text(encoding="utf-8") == result
        assert "gerar_video" not in vars(run)
    finally:
        sys.modules.pop("pipeline.run", None)


def test_cli_uses_uploaded_document_and_keeps_gate(monkeypatch, tmp_path):
    run = importlib.import_module("pipeline.run")
    original = tmp_path / "original.pdf"
    resolver = Mock(return_value=original)
    generate = Mock(return_value=("1. Consultar.", "CENA 1\nNarração: Consultar."))
    monkeypatch.setattr(run, "document_path", resolver)
    monkeypatch.setattr(run, "generate_script", generate)
    monkeypatch.setattr(run, "__file__", str(tmp_path / "pipeline" / "run.py"))
    monkeypatch.setattr(sys, "argv", ["pipeline.run", "--documento-id", "1"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    run.main()
    assert resolver.call_args.args[0] == 1
    generate.assert_called_once_with(str(original))
    generate.reset_mock()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit, match="terminal interativo"):
        run.main()
    generate.assert_not_called()
