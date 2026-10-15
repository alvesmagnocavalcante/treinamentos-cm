import json
from io import BytesIO

import httpx
import pymupdf
import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Documento
from app.services.errors import ServiceError
from app.services.rag import NOT_FOUND
from app.services.roteiro import document_path


def make_pdf():
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.new_page()
        pdf.new_page().insert_text((40, 50), "DEMONSTRACAO FICTICIA. Early check-in: consultar disponibilidade antes de confirmar.")
        return pdf.tobytes()


@pytest.fixture
def flow(tmp_path):
    settings = Settings(tmp_path / "db.sqlite3", documents_path=tmp_path / "documents", vector_path=tmp_path / "vectors",
                        google_api_key="fake-google", openrouter_api_key="fake-router", embedding_dimensions=3)
    calls = []
    state = {"fail_embeddings": False}

    def handler(request):
        data = json.loads(request.content)
        calls.append((str(request.url), data))
        if "googleapis.com" in str(request.url):
            if state["fail_embeddings"]:
                return httpx.Response(429, json={"error": "limit"})
            vectors = []
            for item in data["requests"]:
                text = item["content"]["parts"][0]["text"].lower()
                vectors.append({"values": [0, 0, 1] if "salário" in text else [1, 0, 0]})
            return httpx.Response(200, json={"embeddings": vectors})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Consulte a disponibilidade antes de confirmar [1]."}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as provider, TestClient(create_app(settings)) as client:
        client.app.state.documents.embeddings.client = provider
        client.app.state.rag.llm.client = provider
        client.post("/admin/setores", data={"nome": "Recepção"})
        for title in ("Early Check-in", "Financeiro"):
            client.post("/admin/treinamentos", data={"setor_id": 1, "titulo": title, "ativo": "true"})
        yield client, settings, calls, state


def upload(client, training=1):
    return client.post(f"/admin/treinamentos/{training}/documentos",
                       files={"arquivo": ("POP_EARLY_CHECKIN.pdf", make_pdf(), "application/pdf")}, follow_redirects=False)


def test_pdf_upload_to_chat_with_real_chroma_and_mocked_apis(flow):
    client, settings, calls, _ = flow
    assert upload(client).status_code == 303
    assert upload(client, training=2).status_code == 303
    response = client.post("/treinamentos/1/perguntar", json={"pergunta": "O que devo fazer quando o hóspede chega antes do horário?"})
    assert response.status_code == 200
    result = response.json()
    assert "disponibilidade" in result["resposta"]
    assert len(result["fontes"]) == 1
    assert result["fontes"][0]["pagina"] == 3
    assert result["fontes"][0]["documento"] == "POP_EARLY_CHECKIN.pdf"
    assert result["fontes"][0]["documento_id"] == 1
    llm_calls = [payload for url, payload in calls if "openrouter.ai" in url]
    assert len(llm_calls) == 1
    assert len(json.loads(llm_calls[0]["messages"][1]["content"])["CONTEXTO"]) == 1
    download = client.get("/documentos/1/arquivo")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")
    assert document_path(1, settings).read_bytes() == download.content
    assert client.post("/admin/documentos/1/reindexar").status_code == 200
    assert client.app.state.documents.store.collection.count() == 2
    assert "Indexado" in client.get("/admin/treinamentos/1/documentos").text


def test_no_docs_or_unrelated_question_abstains(flow):
    client, _, calls, _ = flow
    assert client.post("/treinamentos/1/perguntar", json={"pergunta": "Como proceder?"}).json() == {"resposta": NOT_FOUND, "fontes": []}
    assert not calls
    upload(client)
    result = client.post("/treinamentos/1/perguntar", json={"pergunta": "Qual é o salário?"}).json()
    assert result == {"resposta": NOT_FOUND, "fontes": []}
    assert not any("openrouter.ai" in url for url, _ in calls)


def test_failed_index_keeps_pending_file_then_can_retry(flow):
    client, settings, calls, state = flow
    state["fail_embeddings"] = True
    assert upload(client).status_code == 429
    with client.app.state.session_factory() as session:
        doc = session.get(Documento, 1)
        assert doc.processado is False
        assert (settings.documents_path / doc.caminho).exists()
    before = len(calls)
    assert client.post("/treinamentos/1/perguntar", json={"pergunta": "Como proceder?"}).json()["resposta"] == NOT_FOUND
    assert len(calls) == before
    state["fail_embeddings"] = False
    assert client.post("/admin/documentos/1/reindexar").status_code == 200
    with client.app.state.session_factory() as session:
        assert session.get(Documento, 1).processado is True
    state["fail_embeddings"] = True
    assert client.post("/admin/documentos/1/reindexar").status_code == 429
    assert client.post("/treinamentos/1/perguntar", json={"pergunta": "Como proceder?"}).json()["resposta"] == NOT_FOUND


def test_delete_removes_file_metadata_and_vectors(flow):
    client, settings, _, _ = flow
    upload(client)
    path = document_path(1, settings)
    assert client.post("/admin/documentos/1/excluir").status_code == 200
    assert not path.exists()
    assert client.app.state.documents.store.collection.count() == 0
    with client.app.state.session_factory() as session:
        assert session.get(Documento, 1) is None
    assert client.get("/documentos/1/arquivo").status_code == 404
    with pytest.raises(ServiceError):
        document_path(1, settings)


def test_docx_upload_and_question(flow):
    client, _, _, _ = flow
    document = Document()
    document.add_heading("Early Check-in", level=1)
    document.add_paragraph("Consultar disponibilidade antes de confirmar.")
    stream = BytesIO()
    document.save(stream)
    response = client.post("/admin/treinamentos/1/documentos", files={"arquivo": (
        "POP.docx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )})
    assert response.status_code == 200
    result = client.post("/treinamentos/1/perguntar", json={"pergunta": "Como proceder?"}).json()
    assert result["fontes"][0]["pagina"] is None
    assert result["fontes"][0]["secao"] == "Early Check-in"


@pytest.mark.parametrize("payload", [{}, {"pergunta": " "}, {"pergunta": "a" * 2001}, {"pergunta": "ok", "training_id": 2}])
def test_question_validation(flow, payload):
    client, _, _, _ = flow
    assert client.post("/treinamentos/1/perguntar", json=payload).status_code == 422


def test_endpoint_scope_origin_and_upload_limit(flow):
    client, _, _, _ = flow
    assert client.post("/treinamentos/999/perguntar", json={"pergunta": "Teste"}).status_code == 404
    assert client.post("/treinamentos/1/perguntar", json={"pergunta": "Teste"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/admin/treinamentos/1/documentos", content=b"", headers={
        "Content-Type": "multipart/form-data; boundary=test", "Content-Length": str(20 * 1024 * 1024),
    }).status_code == 413
    assert client.post("/admin/treinamentos/1/documentos", files={"arquivo": ("../bad.pdf", b"%PDF-", "application/pdf")}).status_code == 422
