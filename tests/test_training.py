import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.main import create_app
from app.models import Documento, Setor, Treinamento


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(tmp_path / "training.sqlite3"))) as client:
        yield client


def create_training(client, **overrides):
    client.post("/admin/setores", data={"nome": "Recepção"})
    data = {"setor_id": 1, "titulo": "Early Check-in", "ativo": "true"}
    return client.post("/admin/treinamentos", data=data | overrides, follow_redirects=False)


def test_empty_pages_and_static(client):
    assert "Nenhum setor cadastrado" in client.get("/").text
    assert "Novo setor" in client.get("/admin").text
    assert client.get("/static/app.css").status_code == 200


def test_training_and_document_relationship(client):
    response = create_training(client, conteudo="Consultar disponibilidade antes de confirmar.")
    assert response.status_code == 303
    assert response.headers["location"] == "/treinamentos/1"
    assert "Early Check-in" in client.get("/").text
    with client.app.state.session_factory() as session:
        session.add(Documento(
            treinamento_id=1, nome="POP_EARLY_CHECKIN.pdf",
            caminho="media/documentos/test.pdf", tipo="pdf",
        ))
        session.commit()
        documento = session.scalar(select(Documento))
        assert documento.processado is False
        assert documento.criado_em is not None
        assert documento.treinamento.setor.nome == "Recepção"
    page = client.get("/treinamentos/1")
    assert page.status_code == 200
    assert "Consultar disponibilidade" in page.text
    assert "POP_EARLY_CHECKIN.pdf" in page.text
    assert "Pendente de processamento" in page.text
    assert "media/documentos/test.pdf" not in page.text


@pytest.mark.parametrize("data", [{"nome": "   "}, {"nome": "a" * 101}, {}])
def test_sector_validation(client, data):
    assert client.post("/admin/setores", data=data).status_code == 422


def test_duplicate_sector(client):
    assert client.post("/admin/setores", data={"nome": "Recepção"}).status_code == 200
    assert client.post("/admin/setores", data={"nome": " Recepção "}).status_code == 409


@pytest.mark.parametrize("overrides, status", [
    ({"setor_id": 999}, 404), ({"setor_id": -1}, 422),
    ({"titulo": "  "}, 422), ({"titulo": "a" * 201}, 422),
])
def test_training_validation(client, overrides, status):
    assert create_training(client, **overrides).status_code == status


def test_inactive_and_missing_training(client):
    create_training(client, ativo="false")
    assert "Early Check-in" not in client.get("/").text
    assert client.get("/treinamentos/1").status_code == 404
    assert client.get("/treinamentos/999").status_code == 404


def test_user_content_is_escaped(client):
    create_training(client, titulo="<script>alert(1)</script>", conteudo="<img src=x onerror=alert(1)>")
    page = client.get("/treinamentos/1").text
    assert "<script>" not in page
    assert "<img src=x" not in page
    assert "&lt;script&gt;" in page


def test_sqlite_constraints(client):
    with client.app.state.session_factory() as session:
        session.add(Treinamento(setor_id=999, titulo="Órfão"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(Setor(nome="Recepção"))
        session.flush()
        training = Treinamento(setor_id=1, titulo="Check-in")
        session.add(training)
        session.flush()
        session.add(Documento(treinamento_id=training.id, nome="file.exe", caminho="x", tipo="exe"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_database_persists_across_restarts(tmp_path):
    settings = Settings(tmp_path / "persistent.sqlite3")
    with TestClient(create_app(settings)) as client:
        create_training(client)
    with TestClient(create_app(settings)) as client:
        assert "Early Check-in" in client.get("/").text
