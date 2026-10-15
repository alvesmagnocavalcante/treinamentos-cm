from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Documento
from app.services.chunking import chunk_sections
from app.services.embeddings import EmbeddingService
from app.services.errors import ServiceError
from app.services.ingest import extract_text, stored_path
from app.services.vector_store import VectorStore


class DocumentService:
    def __init__(self, settings: Settings, embeddings: EmbeddingService, store: VectorStore):
        self.settings, self.embeddings, self.store = settings, embeddings, store

    def index(self, document: Documento, session: Session) -> int:
        # SQLite é a fonte do status; documentos pendentes nunca entram no RAG.
        document.processado = False
        session.commit()
        path = stored_path(self.settings.documents_path, document.caminho)
        sections = extract_text(path)
        chunks = chunk_sections(sections, self.settings.chunk_tokens, self.settings.overlap_tokens)
        if len(chunks) > 1000:
            raise ServiceError("Documento excede o limite de 1000 chunks.", 422)
        vectors = self.embeddings.embed_documents([chunk.text for chunk in chunks])
        self.store.replace_document(document.id, chunks, vectors, {
            "documento": document.nome, "treinamento_id": document.treinamento_id,
            "setor": document.treinamento.setor.nome,
        })
        document.processado = True
        session.commit()
        return len(chunks)

    def delete(self, document: Documento, session: Session) -> None:
        document.processado = False
        session.commit()
        self.store.remove_document(document.id)
        # Se já estiver ausente, permite finalizar a remoção dos metadados.
        path = (self.settings.documents_path / document.caminho).resolve()
        if path.parent != self.settings.documents_path.resolve():
            raise ServiceError("Caminho do documento inválido.", 422)
        path.unlink(missing_ok=True)
        session.delete(document)
        session.commit()
