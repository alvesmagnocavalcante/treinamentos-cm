"""Leitura autenticada do Drive; não altera arquivos nem permissões na origem."""

import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from urllib.parse import urlsplit

import google.auth
import requests
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession

from app.services.errors import ServiceError

API = "https://www.googleapis.com/drive/v3/files"
SCOPE = "https://www.googleapis.com/auth/drive.readonly"
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
GOOGLE_DOC = "application/vnd.google-apps.document"
FOLDER = "application/vnd.google-apps.folder"
FILE_FIELDS = "id,name,mimeType,version,size,trashed"
MAX_FILES = 100


def folder_id(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"[\w-]{10,200}", value, flags=re.ASCII):
        return value
    try:
        url = urlsplit(value)
        match = re.fullmatch(r"/drive/(?:u/\d+/)?folders/([\w-]{10,200})/?", url.path, re.ASCII)
        if (url.scheme == "https" and url.netloc == "drive.google.com" and match):
            return match[1]
    except ValueError:
        pass
    raise ServiceError("Informe o link de uma pasta do Google Drive ou seu ID.", 422)


def normalize_folder_url(value: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id(value)}" if value.strip() else ""


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime: str
    version: str
    size: int

    @classmethod
    def from_json(cls, item):
        try:
            file = cls(item["id"], item["name"], item["mimeType"], str(item["version"]), int(item.get("size", 0)))
            if (not isinstance(file.name, str) or not isinstance(file.mime, str)
                    or not re.fullmatch(r"[\w-]{10,200}", file.id, re.ASCII) or not file.name
                    or not file.version.isdecimal() or len(file.version) > 40 or file.size < 0):
                raise ValueError
            return file
        except (KeyError, TypeError, ValueError):
            raise ServiceError("O Drive retornou dados de arquivo inválidos.", 502) from None


class DriveClient:
    def __init__(self, session, timeout: float, max_bytes: int):
        self.session, self.timeout, self.max_bytes = session, timeout, max_bytes

    @classmethod
    @contextmanager
    def connect(cls, settings):
        try:
            credentials, _ = google.auth.default(scopes=[SCOPE])
            with AuthorizedSession(credentials, refresh_timeout=settings.timeout_seconds) as session:
                yield cls(session, settings.timeout_seconds, settings.max_upload_bytes)
        except GoogleAuthError:
            raise ServiceError("Configure as credenciais do Google Drive e compartilhe a pasta com a conta de serviço.", 503) from None

    @contextmanager
    def response(self, path="", **params):
        try:
            with self.session.get(API + path, params=params, stream=True, timeout=self.timeout, allow_redirects=False) as response:
                if response.status_code == 429:
                    raise ServiceError("Limite do Google Drive atingido. Tente novamente mais tarde.", 429)
                if response.status_code in (401, 403, 404):
                    raise ServiceError("Não foi possível acessar a pasta ou arquivo. Confira o link, a Drive API e o acesso da conta de serviço.", 422)
                if response.status_code != 200:
                    raise ServiceError("Google Drive indisponível. Tente novamente.", 502)
                yield response
        except requests.RequestException:
            raise ServiceError("Falha de conexão com o Google Drive. Tente novamente.", 503) from None

    def metadata(self, path="", **params):
        with self.response(path, **params) as response:
            try:
                # Também limita respostas de metadados; não carrega corpos sem limite.
                data = bytearray()
                for block in response.iter_content(64 * 1024):
                    data.extend(block)
                    if len(data) > 1024 * 1024:
                        raise ValueError
                payload = json.loads(data)
                if not isinstance(payload, dict):
                    raise ValueError
                return payload
            except (ValueError, TypeError):
                raise ServiceError("O Drive retornou uma resposta inválida.", 502) from None

    def get_document(self, identifier: str) -> DriveFile:
        if not re.fullmatch(r"[\w-]{10,200}", identifier, re.ASCII):
            raise ServiceError("ID de documento do Drive inválido.", 422)
        payload = self.metadata(f"/{identifier}", fields=FILE_FIELDS, supportsAllDrives="true")
        if payload.get("trashed"):
            raise ServiceError("O documento foi removido do Drive.", 404)
        file = DriveFile.from_json(payload)
        if file.mime not in (PDF, DOCX, GOOGLE_DOC):
            raise ServiceError("Formato do Drive não suportado.", 415)
        return file

    def list_documents(self, folder: str) -> list[DriveFile]:
        identifier = folder_id(folder)
        metadata = self.metadata(f"/{identifier}", fields="id,mimeType,trashed", supportsAllDrives="true")
        if metadata.get("mimeType") != FOLDER or metadata.get("trashed"):
            raise ServiceError("O link precisa apontar para uma pasta ativa do Google Drive.", 422)
        query = f"'{identifier}' in parents and trashed = false and (" + " or ".join(
            f"mimeType = '{mime}'" for mime in (PDF, DOCX, GOOGLE_DOC)
        ) + ")"
        files, token, seen = [], None, set()
        while True:
            params = dict(q=query, fields=f"nextPageToken,incompleteSearch,files({FILE_FIELDS})", pageSize=100,
                          supportsAllDrives="true", includeItemsFromAllDrives="true", orderBy="name")
            if token:
                params["pageToken"] = token
            payload = self.metadata(**params)
            if payload.get("incompleteSearch") or not isinstance(payload.get("files"), list):
                raise ServiceError("Não foi possível listar a pasta completa do Drive.", 502)
            files.extend(DriveFile.from_json(item) for item in payload["files"])
            if len(files) > MAX_FILES:
                raise ServiceError("Use uma pasta com até 100 documentos por treinamento.", 422)
            token = payload.get("nextPageToken")
            if not token:
                return files
            if not isinstance(token, str) or token in seen or len(seen) >= MAX_FILES:
                raise ServiceError("O Drive retornou paginação inválida.", 502)
            seen.add(token)

    @contextmanager
    def download(self, file: DriveFile):
        if file.mime not in (PDF, DOCX, GOOGLE_DOC):
            raise ServiceError("Formato do Drive não suportado.", 415)
        if file.size > self.max_bytes:
            raise ServiceError("Arquivo do Drive excede o tamanho máximo permitido.", 413)
        path, params = f"/{file.id}", {"alt": "media", "supportsAllDrives": "true"}
        mime, name = file.mime, file.name
        if file.mime == GOOGLE_DOC:
            path, params, mime = f"/{file.id}/export", {"mimeType": DOCX}, DOCX
            name += ".docx"
        extension = ".pdf" if mime == PDF else ".docx"
        if not name.lower().endswith(extension):
            name += extension
        with self.response(path, **params) as response, SpooledTemporaryFile(max_size=1024 * 1024) as output:
            size = 0
            for block in response.iter_content(64 * 1024):
                size += len(block)
                if size > self.max_bytes:
                    raise ServiceError("Arquivo do Drive excede o tamanho máximo permitido.", 413)
                output.write(block)
            output.seek(0)
            yield DriveUpload(name, mime, output)


@dataclass
class DriveUpload:
    name: str
    content_type: str
    stream: object

    def read(self, size=-1):
        return self.stream.read(size)
