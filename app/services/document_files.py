from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.drive import DOCX, PDF, DriveClient, DriveUpload
from app.services.errors import ServiceError
from app.services.ingest import save_upload


@contextmanager
def document_path(document, config):
    if document.drive_file_id:
        with DriveClient.connect(config) as drive:
            remote = drive.get_document(document.drive_file_id)
            with drive.download(remote) as upload, TemporaryDirectory(prefix="carmel-document-") as directory:
                path, _ = save_upload(upload, Path(directory), config.max_upload_bytes)
                yield path
    elif document.arquivo is not None:
        with BytesIO(document.arquivo) as stream, TemporaryDirectory(prefix="carmel-document-") as directory:
            upload = DriveUpload(document.nome, PDF if document.tipo == "pdf" else DOCX, stream)
            path, _ = save_upload(upload, Path(directory), config.max_upload_bytes)
            yield path
    else:
        raise ServiceError("Documento sem arquivo original disponível.", 404)
