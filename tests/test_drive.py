import json
from contextlib import contextmanager
from io import BytesIO
from unittest.mock import Mock

import google.auth
import pymupdf
import pytest
import requests
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import Client
from docx import Document
from google.auth.exceptions import DefaultCredentialsError

from app import runtime
from app.models import Documento, Setor, Treinamento
from app.services.documents import DocumentService
from app.services.drive import API, DOCX, FOLDER, GOOGLE_DOC, PDF, SCOPE, DriveClient, DriveFile, folder_id
from app.services.drive_sync import DriveSyncService
from app.services.errors import ServiceError

FOLDER_ID = "folder_123456789"
FILE_ID = "document_123456789"
FOLDER_URL = f"https://drive.google.com/drive/folders/{FOLDER_ID}"


def pdf_bytes(text="Procedimento: consultar disponibilidade antes de confirmar."):
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((40, 50), text)
        return pdf.tobytes()


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    result._content_consumed = True
    return result


def remote_file(**kwargs):
    return {"id": FILE_ID, "name": "Procedimento.pdf", "mimeType": PDF, "version": "1", **kwargs}


def drive_client(handler, max_bytes=10 * 1024 * 1024):
    session = Mock()
    session.get.side_effect = handler
    return DriveClient(session, timeout=15, max_bytes=max_bytes)


@pytest.mark.parametrize("value", [FOLDER_ID, FOLDER_URL, FOLDER_URL + "?usp=sharing", f"https://drive.google.com/drive/u/0/folders/{FOLDER_ID}"])
def test_folder_links_and_id(value):
    assert folder_id(value) == FOLDER_ID


@pytest.mark.parametrize("value", ["", "' or trashed=true", "http://drive.google.com/drive/folders/" + FOLDER_ID,
                                     "https://drive.google.com.evil.test/drive/folders/" + FOLDER_ID,
                                     "https://user@drive.google.com/drive/folders/" + FOLDER_ID,
                                     "https://drive.google.com/file/d/" + FILE_ID + "/view", "http://127.0.0.1/"])
def test_reject_unsafe_or_nonfolder_links(value):
    with pytest.raises(ServiceError):
        folder_id(value)


def test_pagination_shared_drives_and_only_supported_documents():
    def handler(url, **kwargs):
        assert url.startswith(API)
        assert kwargs["allow_redirects"] is False
        assert kwargs["timeout"] == 15
        params = kwargs["params"]
        assert params["supportsAllDrives"] == "true"
        if url.endswith(FOLDER_ID):
            return response({"mimeType": FOLDER, "trashed": False})
        assert params["includeItemsFromAllDrives"] == "true"
        assert f"'{FOLDER_ID}' in parents" in params["q"]
        assert "trashed = false" in params["q"]
        assert GOOGLE_DOC in params["q"]
        if params.get("pageToken") == "second":
            return response({"files": [remote_file(id="another_12345678", mimeType=DOCX)]})
        return response({"files": [remote_file()], "nextPageToken": "second"})

    drive = drive_client(handler)
    assert len(drive.list_documents(FOLDER_URL)) == 2
    assert drive.session.get.call_count == 3


@pytest.mark.parametrize("payload", [
    {"files": [], "incompleteSearch": True},
    {"files": [remote_file()] * 101},
    {"files": [remote_file(id="../bad-path")]},
    {"files": [remote_file(name=123)]},
    {"files": [remote_file(version=None)]},
    {"files": "invalid"},
])
def test_invalid_or_excessive_listing_is_rejected(payload):
    results = iter([response({"mimeType": FOLDER}), response(payload)])
    with pytest.raises(ServiceError):
        drive_client(lambda *args, **kwargs: next(results)).list_documents(FOLDER_URL)


def test_repeated_page_token_is_rejected():
    results = iter([response({"mimeType": FOLDER}), response({"files": [], "nextPageToken": "same"}),
                    response({"files": [], "nextPageToken": "same"})])
    with pytest.raises(ServiceError, match="paginação"):
        drive_client(lambda *args, **kwargs: next(results)).list_documents(FOLDER_URL)


@pytest.mark.parametrize("status,expected", [(401, 422), (403, 422), (404, 422), (429, 429), (500, 502), (302, 502)])
def test_google_errors_do_not_expose_response(status, expected):
    drive = drive_client(lambda *args, **kwargs: response(b"secret-provider-response", status))
    with pytest.raises(ServiceError) as exc:
        drive.list_documents(FOLDER_URL)
    assert exc.value.status_code == expected
    assert "secret-provider-response" not in str(exc.value)


def test_network_failure_is_safe():
    def fail(*args, **kwargs):
        raise requests.Timeout("private-auth-detail")

    with pytest.raises(ServiceError, match="Falha de conexão"):
        drive_client(fail).list_documents(FOLDER_URL)


def test_adc_missing_credentials(monkeypatch, platform_settings):
    def fail(**kwargs):
        assert kwargs["scopes"] == [SCOPE]
        raise DefaultCredentialsError("private-credential-details")

    monkeypatch.setattr(google.auth, "default", fail)
    with pytest.raises(ServiceError, match="Configure as credenciais"):
        with DriveClient.connect(platform_settings):
            pytest.fail("Não deve abrir uma sessão sem credenciais")


def test_download_google_doc_exports_docx_and_closes_stream():
    doc = Document()
    doc.add_paragraph("Procedimento interno de atendimento.")
    buffer = BytesIO()
    doc.save(buffer)

    def handler(url, **kwargs):
        assert url == f"{API}/{FILE_ID}/export"
        assert kwargs["params"] == {"mimeType": DOCX}
        return response(buffer.getvalue())

    with drive_client(handler).download(DriveFile.from_json(remote_file(mimeType=GOOGLE_DOC, name="Procedimento"))) as upload:
        assert upload.name == "Procedimento.docx"
        assert upload.content_type == DOCX
        assert upload.read().startswith(b"PK")
    assert upload.stream.closed


@pytest.mark.parametrize("declared_size,body", [(11, b"small"), (0, b"x" * 11)])
def test_download_limits_declared_and_streamed_bytes(declared_size, body):
    drive = drive_client(lambda *args, **kwargs: response(body), max_bytes=10)
    with pytest.raises(ServiceError) as exc:
        with drive.download(DriveFile.from_json(remote_file(size=declared_size))):
            pytest.fail("Não deve aceitar arquivo acima do limite")
    assert exc.value.status_code == 413


@pytest.fixture
def sync_flow(platform_settings, monkeypatch):
    training = Treinamento.objects.create(titulo="Integração", setor=Setor.objects.create(nome="RH"))
    embeddings = Mock()
    embeddings.embed_documents.return_value = [[1.0, 0.0, 0.0]]
    store = Mock()
    documents = DocumentService(platform_settings, embeddings, store)
    state = {"file": remote_file(), "body": pdf_bytes()}

    def handler(url, **kwargs):
        if url.endswith(FOLDER_ID):
            return response({"mimeType": FOLDER})
        if url == API:
            return response({"files": [state["file"]]})
        return response(state["body"])

    drive = drive_client(handler)
    return training, documents, drive, state


@pytest.mark.django_db
def test_sync_indexes_skips_and_updates_in_place(sync_flow):
    training, documents, drive, state = sync_flow
    sync = DriveSyncService(documents, drive)
    assert sync.sync(training, FOLDER_URL).indexed == 1
    document = Documento.objects.get()
    first_id, first_path = document.pk, documents.settings.documents_path / document.caminho
    assert document.processado and document.drive_file_id == FILE_ID
    assert first_path.is_file()
    assert documents.store.replace_document.call_args.args[3]["treinamento_id"] == training.pk
    assert sync.sync(training, FOLDER_URL).unchanged == 1
    assert documents.embeddings.embed_documents.call_count == 1
    state["file"] = remote_file(version="2", name="Atualizado.pdf")
    state["body"] = pdf_bytes("Nova regra: consultar a recepcao.")
    assert sync.sync(training, FOLDER_URL).indexed == 1
    document.refresh_from_db()
    assert document.pk == first_id and document.nome == "Atualizado.pdf" and document.drive_version == "2"
    assert document.processado
    assert not first_path.exists()
    assert Documento.objects.count() == 1
    assert documents.embeddings.embed_documents.call_count == 2


@pytest.mark.django_db
def test_failed_embedding_keeps_pending_document_for_retry(sync_flow):
    training, documents, drive, state = sync_flow
    documents.embeddings.embed_documents.side_effect = ServiceError("Limite atingido", 429)
    sync = DriveSyncService(documents, drive)
    with pytest.raises(ServiceError):
        sync.sync(training, FOLDER_URL)
    document = Documento.objects.get()
    assert not document.processado
    assert (documents.settings.documents_path / document.caminho).is_file()
    documents.embeddings.embed_documents.side_effect = None
    assert sync.sync(training, FOLDER_URL).indexed == 1
    assert Documento.objects.get().processado


@pytest.mark.django_db
def test_missing_local_copy_is_downloaded_again(sync_flow):
    training, documents, drive, state = sync_flow
    sync = DriveSyncService(documents, drive)
    sync.sync(training, FOLDER_URL)
    document = Documento.objects.get()
    (documents.settings.documents_path / document.caminho).unlink()
    assert sync.sync(training, FOLDER_URL).indexed == 1
    assert Documento.objects.count() == 1


@pytest.mark.django_db
def test_corrupt_download_does_not_create_record_or_orphan_file(sync_flow):
    training, documents, drive, state = sync_flow
    state["body"] = b"<html>Login required</html>"
    with pytest.raises(ServiceError):
        DriveSyncService(documents, drive).sync(training, FOLDER_URL)
    assert not Documento.objects.exists()
    assert not list(documents.settings.documents_path.iterdir())
    documents.embeddings.embed_documents.assert_not_called()


@pytest.mark.django_db
def test_failed_update_disables_old_index_until_retry(sync_flow):
    training, documents, drive, state = sync_flow
    sync = DriveSyncService(documents, drive)
    sync.sync(training, FOLDER_URL)
    original = Documento.objects.get()
    original_path = documents.settings.documents_path / original.caminho
    state["file"] = remote_file(version="2")
    state["body"] = b"invalid pdf"
    with pytest.raises(ServiceError):
        sync.sync(training, FOLDER_URL)
    original.refresh_from_db()
    assert not original.processado
    assert original.drive_version == "1"
    assert original_path.is_file()
    state["body"] = pdf_bytes("Conteudo atualizado para o treinamento.")
    assert sync.sync(training, FOLDER_URL).indexed == 1
    assert Documento.objects.get().processado
    assert not original_path.exists()


@pytest.mark.django_db
def test_database_failure_removes_downloaded_copy(sync_flow, monkeypatch):
    training, documents, drive, state = sync_flow

    def fail(*args, **kwargs):
        raise DatabaseError("simulated")

    monkeypatch.setattr(Documento, "save", fail)
    with pytest.raises(DatabaseError):
        DriveSyncService(documents, drive).sync(training, FOLDER_URL)
    assert not Documento.objects.exists()
    assert not list(documents.settings.documents_path.iterdir())


@pytest.mark.django_db
def test_same_drive_file_is_isolated_per_training(sync_flow):
    training, documents, drive, state = sync_flow
    other = Treinamento.objects.create(titulo="Outro", setor=training.setor)
    sync = DriveSyncService(documents, drive)
    sync.sync(training, FOLDER_URL)
    sync.sync(other, FOLDER_URL)
    assert Documento.objects.count() == 2
    assert set(Documento.objects.values_list("treinamento_id", flat=True)) == {training.pk, other.pk}


@pytest.mark.django_db
def test_sync_never_deletes_files_removed_from_drive(sync_flow):
    training, documents, drive, state = sync_flow
    sync = DriveSyncService(documents, drive)
    sync.sync(training, FOLDER_URL)
    drive.list_documents = lambda folder: []
    assert sync.sync(training, FOLDER_URL).indexed == 0
    assert Documento.objects.count() == 1
    documents.store.remove_document.assert_not_called()


@pytest.mark.django_db
def test_sync_endpoint_permissions_csrf_and_result(sync_flow, staff_client, monkeypatch, django_user_model):
    training, documents, drive, state = sync_flow
    url = f"/admin/treinamentos/{training.pk}/documentos/drive"

    @contextmanager
    def connect(config):
        yield drive

    @contextmanager
    def services():
        yield documents, None

    monkeypatch.setattr(DriveClient, "connect", connect)
    monkeypatch.setattr(runtime, "services", services)
    client = Client()
    employee = django_user_model.objects.create(username="colaborador_drive")
    client.force_login(employee)
    assert client.post(url, {"pasta": FOLDER_URL}).status_code == 302
    limited = django_user_model.objects.create(username="limitado", is_staff=True)
    limited.user_permissions.add(Permission.objects.get(codename="view_documento"), Permission.objects.get(codename="add_documento"))
    client.force_login(limited)
    assert client.post(url, {"pasta": FOLDER_URL}).status_code == 403
    assert not Documento.objects.exists()
    assert staff_client.get(url).status_code == 405
    assert staff_client.post(url, {"pasta": "https://evil.test"}).status_code == 422
    assert staff_client.post(url, {}).status_code == 422
    result = staff_client.post(url, {"pasta": FOLDER_URL}, follow=True)
    assert result.status_code == 200
    assert "Drive sincronizado: 1" in result.content.decode()
    assert Documento.objects.get().processado
    training.refresh_from_db()
    assert training.drive_folder_url == FOLDER_URL

    secured = Client(enforce_csrf_checks=True)
    secured.force_login(django_user_model.objects.get(username="gestor"))
    assert secured.post(url, {"pasta": FOLDER_URL}).status_code == 403


@pytest.mark.django_db
def test_sync_endpoint_handles_auth_error(sync_flow, staff_client, monkeypatch):
    training, documents, drive, state = sync_flow

    @contextmanager
    def connect(config):
        raise ServiceError("Configure as credenciais", 503)
        yield

    monkeypatch.setattr(DriveClient, "connect", connect)
    response = staff_client.post(f"/admin/treinamentos/{training.pk}/documentos/drive", {"pasta": FOLDER_URL})
    assert response.status_code == 503
    assert "Configure as credenciais" in response.content.decode()
    assert not Documento.objects.exists()


def test_training_validates_folder_url():
    training = Treinamento(titulo="Integração", drive_folder_url="https://evil.test")
    with pytest.raises(ValidationError):
        training.clean()
    training.drive_folder_url = FOLDER_URL + "?usp=sharing"
    training.clean()
    assert training.drive_folder_url == FOLDER_URL
