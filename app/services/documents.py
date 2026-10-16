from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.models import Documento, Treinamento
from app.services.chunking import chunk_sections
from app.services.embeddings import EmbeddingService
from app.services.errors import ServiceError
from app.services.ingest import UploadedDocument, extract_text, save_upload
from app.services.vector_store import VectorStore
from app.services.document_files import document_path


class DocumentService:
    def __init__(self, settings: Settings, embeddings: EmbeddingService, store: VectorStore):
        self.settings, self.embeddings, self.store = settings, embeddings, store

    def upload(self, training: Treinamento, upload: UploadedDocument) -> Documento:
        with TemporaryDirectory(prefix="carmel-upload-") as directory:
            path, name = save_upload(upload, Path(directory), self.settings.max_upload_bytes)
            return Documento.objects.create(
                treinamento=training, nome=name, tipo=path.suffix[1:], arquivo=path.read_bytes(),
            )

    def index(self, document: Documento, source_path: Path | None = None) -> int:
        # O banco relacional controla quais documentos podem entrar no RAG.
        document.processado = False
        document.save(update_fields=["processado"])
        with (nullcontext(source_path) if source_path is not None else document_path(document, self.settings)) as path:
            sections = extract_text(path)
        chunks = chunk_sections(sections, self.settings.chunk_tokens, self.settings.overlap_tokens)
        if len(chunks) > 1000:
            raise ServiceError("Documento excede o limite de 1000 chunks.", 422)
        vectors = self.embeddings.embed_documents([chunk.text for chunk in chunks])
        self.store.replace_document(document.pk, chunks, vectors, {
            "documento": document.nome, "treinamento_id": document.treinamento_id,
            "setor": document.treinamento.setor.nome,
        })
        document.processado = True
        document.save(update_fields=["processado"])
        return len(chunks)

    def delete(self, document: Documento) -> None:
        document.delete()
