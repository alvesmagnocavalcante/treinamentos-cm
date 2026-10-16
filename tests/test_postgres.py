import json
from contextlib import contextmanager
from dataclasses import replace
from io import StringIO
from types import SimpleNamespace

import httpx
import pymupdf
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection

from app import runtime
from app.models import Documento, DocumentoTrecho, Setor, Treinamento
from app.services.chunking import Chunk
from app.services.documents import DocumentService
from app.services.drive import DriveClient, DriveFile
from app.services.embeddings import EmbeddingService
from app.services.errors import ServiceError
from app.services.llm import LLMService
from app.services.vector_store import VectorStore
from app.services.rag import RagService

pytestmark = pytest.mark.django_db
FOLDER = "https://drive.google.com/drive/folders/folder_123456789"


def pdf_bytes(text="Consulte a disponibilidade antes de confirmar o early check-in."):
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((40, 50), text)
        return pdf.tobytes()


@pytest.fixture
def pg_flow(tmp_path, settings, monkeypatch):
    config = replace(settings.SERVICE_SETTINGS, google_api_key="offline-google", openrouter_api_key="offline-router", embedding_dimensions=3)
    settings.SERVICE_SETTINGS = config
    store = VectorStore(config)
    training = Treinamento.objects.create(titulo="Integração", setor=Setor.objects.create(nome="RH"))
    calls, state = [], {"fail": False}

    def handler(request):
        payload = json.loads(request.content)
        calls.append(str(request.url))
        if "googleapis.com" in str(request.url):
            if state["fail"]:
                return httpx.Response(429, json={"error": "limit"})
            return httpx.Response(200, json={"embeddings": [{"values": [1, 0, 0]} for _ in payload["requests"]]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Consulte a disponibilidade antes de confirmar [1]."}}]})

    @contextmanager
    def services():
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            embeddings = EmbeddingService(config, client)
            yield DocumentService(config, embeddings, store), RagService(embeddings, store, LLMService(config, client), config.max_distance)

    monkeypatch.setattr(runtime, "services", services)
    monkeypatch.setattr(runtime, "store", store)
    return config, store, training, calls, state


def add(store, training, text="Procedimento", vector=None, processed=True):
    document = Documento.objects.create(treinamento=training, nome="POP.pdf", arquivo=pdf_bytes(), tipo="pdf", processado=processed)
    store.replace_document(document.pk, [Chunk(text, 1, "Atendimento")], [vector or [1, 0, 0]], {"treinamento_id": training.pk})
    return document


def test_pgvector_extension_and_nearest_neighbors_are_real(pg_flow):
    config, store, training, calls, state = pg_flow
    with connection.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension WHERE extname='vector'")
        assert cursor.fetchone() == ("vector",)
    near = add(store, training, "Próximo", [1, 0, 0])
    far = add(store, training, "Distante", [0, 1, 0])
    hits = store.search([1, 0, 0], training.pk, [near.pk, far.pk])
    assert [hit.text for hit in hits] == ["Próximo", "Distante"]
    assert hits[0].distance == pytest.approx(0)
    assert hits[1].distance == pytest.approx(1)
    assert hits[0].metadata["pagina"] == 1


def test_postgres_enforces_training_and_processed_scope(pg_flow):
    config, store, training, calls, state = pg_flow
    other = Treinamento.objects.create(titulo="Outro", setor=training.setor)
    allowed = add(store, training)
    pending = add(store, training, "Pendente", processed=False)
    foreign = add(store, other, "Outro setor")
    hits = store.search([1, 0, 0], training.pk, [allowed.pk, pending.pk, foreign.pk])
    assert len(hits) == 1
    assert hits[0].metadata["documento_id"] == allowed.pk
    assert store.search([1, 0, 0], training.pk, []) == []


def test_atomic_replacement_keeps_previous_chunks_on_failure(pg_flow, monkeypatch):
    config, store, training, calls, state = pg_flow
    document = add(store, training, "Original")

    def fail(*args, **kwargs):
        raise DatabaseError("simulated")

    monkeypatch.setattr(DocumentoTrecho.objects, "bulk_create", fail)
    with pytest.raises(DatabaseError):
        store.replace_document(document.pk, [Chunk("Novo", 1, "")], [[1, 0, 0]], {"treinamento_id": training.pk})
    assert store.search([1, 0, 0], training.pk, [document.pk])[0].text == "Original"


def test_changed_embedding_model_requires_reindex(pg_flow):
    config, store, training, calls, state = pg_flow
    document = add(store, training)
    incompatible = VectorStore(replace(config, embedding_model="models/another-model"))
    with pytest.raises(ServiceError, match="outro modelo"):
        incompatible.search([1, 0, 0], training.pk, [document.pk])


@pytest.mark.parametrize("vector", [[0, 0, 0], [1, 0], [float("nan"), 0, 1]])
def test_invalid_vectors_cannot_replace_valid_chunks(pg_flow, vector):
    config, store, training, calls, state = pg_flow
    document = add(store, training)
    with pytest.raises(ServiceError):
        store.replace_document(document.pk, [Chunk("Inválido", 1, "")], [vector], {"treinamento_id": training.pk})
    assert DocumentoTrecho.objects.filter(documento=document).count() == 1


def test_new_upload_persists_in_database_and_can_be_downloaded_without_disk(pg_flow, staff_client):
    config, store, training, calls, state = pg_flow
    data = pdf_bytes()
    response = staff_client.post(f"/admin/treinamentos/{training.pk}/documentos", {"arquivo": SimpleUploadedFile("POP.pdf", data, content_type="application/pdf")})
    assert response.status_code == 302
    document = Documento.objects.get()
    assert bytes(document.arquivo) == data and document.processado
    response = staff_client.get(f"/documentos/{document.pk}/arquivo")
    assert b"".join(response.streaming_content) == data
    answer = staff_client.post(f"/treinamentos/{training.pk}/perguntar", {"pergunta": "Como proceder?"}, content_type="application/json")
    assert "disponibilidade" in answer.json()["resposta"]
    assert staff_client.post(f"/admin/documentos/{document.pk}/reindexar").status_code == 302
    assert DocumentoTrecho.objects.count() == 1
    assert staff_client.post(f"/admin/documentos/{document.pk}/excluir").status_code == 302
    assert not DocumentoTrecho.objects.exists() and not Documento.objects.exists()


def test_drive_sync_chat_download_and_reindex_survive_absent_local_files(pg_flow, staff_client, monkeypatch):
    config, store, training, calls, state = pg_flow
    remote = {"file": DriveFile("document_123456789", "Procedimento.pdf", "application/pdf", "1", 0), "body": pdf_bytes()}

    @contextmanager
    def download(file):
        yield SimpleUploadedFile(file.name, remote["body"], content_type=file.mime)

    @contextmanager
    def connect(config):
        yield SimpleNamespace(list_documents=lambda folder: [remote["file"]],
                              get_document=lambda identifier: remote["file"], download=download)

    monkeypatch.setattr(DriveClient, "connect", connect)
    sync_url = f"/admin/treinamentos/{training.pk}/documentos/drive"
    assert staff_client.post(sync_url, {"pasta": FOLDER}).status_code == 302
    document = Documento.objects.get()
    assert document.processado and document.arquivo is None
    before = len(calls)
    assert staff_client.post(sync_url, {"pasta": FOLDER}).status_code == 302
    assert len(calls) == before
    page = staff_client.get(f"/treinamentos/{training.pk}").content.decode()
    assert f'href="/documentos/{document.pk}/arquivo"' in page
    response = staff_client.post(f"/treinamentos/{training.pk}/perguntar", {"pergunta": "Como proceder?"}, content_type="application/json")
    assert "disponibilidade" in response.json()["resposta"]
    response = staff_client.get(f"/documentos/{document.pk}/arquivo")
    assert b"".join(response.streaming_content).startswith(b"%PDF-")
    assert staff_client.post(f"/admin/documentos/{document.pk}/reindexar").status_code == 302
    assert DocumentoTrecho.objects.count() == 1
    remote["file"] = replace(remote["file"], version="2")
    remote["body"] = pdf_bytes("Nova regra: consultar a recepcao antes de confirmar.")
    assert staff_client.post(sync_url, {"pasta": FOLDER}).status_code == 302
    assert Documento.objects.count() == 1 and DocumentoTrecho.objects.count() == 1
    assert "Nova regra" in DocumentoTrecho.objects.get().texto


def test_failed_embedding_does_not_leave_drive_document_in_rag(pg_flow, staff_client, monkeypatch):
    config, store, training, calls, state = pg_flow
    document = add(store, training)
    state["fail"] = True
    response = staff_client.post(f"/admin/documentos/{document.pk}/reindexar")
    assert response.status_code == 429
    document.refresh_from_db()
    assert not document.processado
    assert store.search([1, 0, 0], training.pk, [document.pk]) == []
    state["fail"] = False
    assert staff_client.post(f"/admin/documentos/{document.pk}/reindexar").status_code == 302
    assert len(store.search([1, 0, 0], training.pk, [document.pk])) == 1


def test_setup_training_is_idempotent_and_never_overwrites_folder(pg_flow):
    config, store, training, calls, state = pg_flow
    output = StringIO()
    call_command("setup_training", drive_folder=FOLDER, stdout=output)
    call_command("setup_training", drive_folder=FOLDER, stdout=output)
    assert Treinamento.objects.count() == 1
    assert not Documento.objects.exists()
    training.refresh_from_db()
    assert training.drive_folder_url == FOLDER
    with pytest.raises(CommandError, match="outra pasta"):
        call_command("setup_training", drive_folder=FOLDER + "other", stdout=output)
