from app.config import Settings
from app.models import Documento, Treinamento
from app.services.chunking import chunk_sections
from app.services.embeddings import EmbeddingService
from app.services.errors import ServiceError
from app.services.ingest import UploadedDocument, extract_text, save_upload, stored_path
from app.services.vector_store import VectorStore


class DocumentService:
    def __init__(self, settings: Settings, embeddings: EmbeddingService, store: VectorStore):
        self.settings, self.embeddings, self.store = settings, embeddings, store

    def upload(self, training: Treinamento, upload: UploadedDocument) -> Documento:
        path, name = save_upload(upload, self.settings.documents_path, self.settings.max_upload_bytes)
        try:
            return Documento.objects.create(
                treinamento=training, nome=name, caminho=path.name, tipo=path.suffix[1:],
            )
        except Exception:
            # Sem registro no banco, o arquivo não pode ficar órfão.
            path.unlink(missing_ok=True)
            raise

    def index(self, document: Documento) -> int:
        # O banco relacional controla quais documentos podem entrar no RAG.
        document.processado = False
        document.save(update_fields=["processado"])
        path = stored_path(self.settings.documents_path, document.caminho)
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
        path = stored_path(self.settings.documents_path, document.caminho, must_exist=False)
        document.processado = False
        document.save(update_fields=["processado"])
        self.store.remove_document(document.pk)
        path.unlink(missing_ok=True)
        document.delete()
