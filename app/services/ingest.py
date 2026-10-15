import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pymupdf
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from fastapi import UploadFile

from app.services.errors import ServiceError

MAX_TEXT = 2_000_000
MAX_PAGES = 300
MAX_UNPACKED = 50 * 1024 * 1024


@dataclass(frozen=True)
class TextSection:
    text: str
    page: int = 0  # DOCX não possui paginação estável.
    section: str = ""


def clean_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def validate_container(path: Path) -> None:
    if path.suffix == ".pdf":
        with path.open("rb") as stream:
            if not stream.read(1024).lstrip().startswith(b"%PDF-"):
                raise ServiceError("O arquivo não possui assinatura PDF válida.", 422)
        return
    try:
        with zipfile.ZipFile(path) as archive:
            files = archive.infolist()
            names = {item.filename for item in files}
            if not {"[Content_Types].xml", "word/document.xml"} <= names:
                raise ValueError
            if len(files) > 2000 or sum(item.file_size for item in files) > MAX_UNPACKED:
                raise ValueError
            if any("vbaproject" in name.lower() for name in names):
                raise ValueError
    except (zipfile.BadZipFile, ValueError, OSError):
        raise ServiceError("DOCX inválido, com macros ou acima do limite de descompressão.", 422) from None


def save_upload(upload: UploadFile, root: Path, max_bytes: int) -> tuple[Path, str]:
    name = (upload.filename or "").strip()
    if not name or len(name) > 255 or any(c in name for c in '/\\:') or any(ord(c) < 32 for c in name):
        raise ServiceError("Nome de arquivo inválido.", 422)
    extension = Path(name).suffix.lower()
    types = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if extension not in types:
        raise ServiceError("Envie somente PDF ou DOCX.", 415)
    if upload.content_type not in (types[extension], "application/octet-stream"):
        raise ServiceError("Tipo de conteúdo incompatível com o arquivo.", 415)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{uuid4().hex}{extension}"
    size = 0
    try:
        with path.open("xb") as output:
            while data := upload.file.read(64 * 1024):
                size += len(data)
                if size > max_bytes:
                    raise ServiceError("Arquivo excede o tamanho máximo permitido.", 413)
                output.write(data)
        if not size:
            raise ServiceError("O arquivo está vazio.", 422)
        validate_container(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path, name


def extract_text(path: Path) -> list[TextSection]:
    validate_container(path)
    sections = []
    try:
        if path.suffix == ".pdf":
            with pymupdf.open(path) as pdf:
                if pdf.needs_pass or len(pdf) > MAX_PAGES:
                    raise ServiceError("PDF protegido por senha ou com mais de 300 páginas.", 422)
                total = 0
                for number, page in enumerate(pdf, 1):
                    text = clean_text("\n\n".join(block[4] for block in page.get_text("blocks", sort=True) if block[6] == 0))
                    total += len(text)
                    if total > MAX_TEXT:
                        raise ServiceError("Documento excede o limite de texto extraído.", 422)
                    if text:
                        sections.append(TextSection(text, page=number))
        elif path.suffix == ".docx":
            doc = Document(path)
            title, paragraphs = "Início", []
            for item in doc.iter_inner_content():
                if isinstance(item, Paragraph):
                    if item.style and item.style.name.startswith("Heading") and item.text.strip():
                        if paragraphs:
                            sections.append(TextSection(clean_text("\n\n".join(paragraphs)), section=title))
                        title, paragraphs = item.text.strip(), []
                    if item.text.strip():
                        paragraphs.append(item.text)
                elif isinstance(item, Table):
                    paragraphs.extend(" | ".join(cell.text for cell in row.cells) for row in item.rows)
            if paragraphs:
                sections.append(TextSection(clean_text("\n\n".join(paragraphs)), section=title))
        else:
            raise ServiceError("Formato não suportado.", 415)
    except ServiceError:
        raise
    except Exception:
        raise ServiceError("Não foi possível ler o documento. Verifique se o arquivo está íntegro.", 422) from None
    sections = [section for section in sections if section.text]
    if not sections:
        raise ServiceError("Documento sem texto extraível. PDFs digitalizados precisam de OCR antes do upload.", 422)
    if sum(len(section.text) for section in sections) > MAX_TEXT:
        raise ServiceError("Documento excede o limite de texto extraído.", 422)
    return sections


def stored_path(root: Path, filename: str) -> Path:
    path = (root / filename).resolve()
    if path.parent != root.resolve() or path.suffix not in (".pdf", ".docx"):
        raise ServiceError("Caminho do documento inválido.", 422)
    if not path.is_file():
        raise ServiceError("Arquivo do documento não encontrado.", 404)
    return path
