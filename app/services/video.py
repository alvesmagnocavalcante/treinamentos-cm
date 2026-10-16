"""Links do Drive e transmissão de vídeos acessíveis sem autenticação Google."""

import re
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from app.services.errors import ServiceError

FILE_PATH = re.compile(r"/file/d/([A-Za-z0-9_-]+)(?:/(?:view|preview))?/?")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]+")


def normalize_video_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    error = "Informe um link HTTPS de arquivo do Google Drive (drive.google.com/file/d/...)."
    try:
        url = urlsplit(value)
    except ValueError:
        raise ServiceError(error, 422) from None
    if (len(value) > 2048 or any(ord(char) < 32 for char in value)
            or url.scheme != "https" or url.netloc != "drive.google.com"):
        raise ServiceError(error, 422)
    query = parse_qs(url.query)
    match = FILE_PATH.fullmatch(url.path)
    file_id = ""
    if match:
        file_id = match.group(1)
    elif url.path == "/open":
        file_id = query.get("id", [""])[0]
    if not IDENTIFIER.fullmatch(file_id):
        raise ServiceError(error, 422)
    resource_key = query.get("resourcekey", [""])[0]
    if resource_key and not IDENTIFIER.fullmatch(resource_key):
        raise ServiceError(error, 422)
    suffix = "?" + urlencode({"resourcekey": resource_key}) if resource_key else ""
    return f"https://drive.google.com/file/d/{file_id}/view{suffix}"


class VideoStream:
    def __init__(self, client: httpx.Client, response: httpx.Response):
        self.client, self.response = client, response

    def __iter__(self):
        try:
            yield from self.response.iter_bytes(chunk_size=64 * 1024)
        finally:
            self.close()

    def close(self):
        try:
            self.response.close()
        finally:
            self.client.close()


def open_video(value: str, byte_range: str, *, method: str = "GET") -> VideoStream:
    match = re.fullmatch(r"bytes=(\d{0,18})-(\d{0,18})", byte_range)
    if not match or not any(match.groups()):
        raise ServiceError("Intervalo de vídeo inválido.", 416)
    start, end = match.groups()
    if (start and end and int(start) > int(end)) or (not start and int(end) == 0):
        raise ServiceError("Intervalo de vídeo inválido.", 416)
    canonical = normalize_video_url(value)
    if not canonical:
        raise ServiceError("Vídeo não encontrado.", 404)
    url = urlsplit(canonical)
    params = {"id": url.path.split("/")[3], "export": "download"}
    params.update({key: values[0] for key, values in parse_qs(url.query).items()})
    client = httpx.Client(timeout=60, follow_redirects=False)
    response = None
    try:
        request = client.build_request(
            method, "https://drive.usercontent.google.com/download",
            params=params, headers={"Range": byte_range, "Accept-Encoding": "identity"},
        )
        response = client.send(request, stream=True)
        if response.status_code == 416:
            raise ServiceError("Intervalo fora do vídeo.", 416)
        if response.status_code not in (200, 206) or not response.headers.get("content-type", "").startswith("video/"):
            raise ServiceError("Não foi possível reproduzir aqui. Use Abrir vídeo para acessar pelo Drive.", 503)
        return VideoStream(client, response)
    except (httpx.HTTPError, ServiceError) as exc:
        if response is not None:
            response.close()
        client.close()
        if isinstance(exc, ServiceError):
            raise
        raise ServiceError("Vídeo temporariamente indisponível. Tente novamente ou abra pelo Drive.", 503) from None
