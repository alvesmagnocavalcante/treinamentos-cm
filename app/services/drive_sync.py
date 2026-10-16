from dataclasses import dataclass

from django.db import transaction

from app.models import Documento
from app.services.drive import normalize_folder_url
from app.services.ingest import save_upload, stored_file_exists, stored_path


@dataclass
class SyncResult:
    indexed: int = 0
    unchanged: int = 0


class DriveSyncService:
    def __init__(self, documents, drive):
        self.documents, self.drive = documents, drive

    def sync(self, training, folder_url: str) -> SyncResult:
        folder_url = normalize_folder_url(folder_url)
        files = self.drive.list_documents(folder_url)
        training.drive_folder_url = folder_url
        training.save(update_fields=["drive_folder_url"])
        result = SyncResult()
        for file in files:
            document = Documento.objects.filter(treinamento=training, drive_file_id=file.id).first()
            config = self.documents.settings
            if (document and document.processado and document.drive_version == file.version
                    and stored_file_exists(config.documents_path, document.caminho)):
                result.unchanged += 1
                continue
            # Conteúdo alterado não pode continuar respondendo pelo índice anterior se a atualização falhar.
            if document:
                document.processado = False
                document.save(update_fields=["processado"])
            old_path = stored_path(config.documents_path, document.caminho, must_exist=False) if document else None
            with self.drive.download(file) as upload:
                path, name = save_upload(upload, config.documents_path, config.max_upload_bytes)
            try:
                with transaction.atomic():
                    if document is None:
                        document = Documento(treinamento=training, drive_file_id=file.id)
                    document.nome, document.caminho, document.tipo = name, path.name, path.suffix[1:]
                    document.drive_version, document.processado = file.version, False
                    document.save()
            except Exception:
                path.unlink(missing_ok=True)
                raise
            if old_path:
                old_path.unlink(missing_ok=True)
            self.documents.index(document)
            result.indexed += 1
        return result
