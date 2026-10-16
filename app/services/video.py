"""Referências de vídeos do Drive; nenhum download ou acesso à API é necessário."""

import re
from urllib.parse import parse_qs, urlencode, urlsplit

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


def video_preview_url(value: str) -> str:
    canonical = normalize_video_url(value)
    if not canonical:
        return ""
    url = urlsplit(canonical)
    return url._replace(path=url.path.removesuffix("/view") + "/preview").geturl()
