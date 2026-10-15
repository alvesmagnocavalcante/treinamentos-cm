import logging
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from app.config import Settings
from app.services.chunking import Chunk
from app.services.errors import ServiceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchHit:
    text: str
    metadata: dict
    distance: float


class VectorStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = RLock()
        self._collection = None
        self._client = None

    @property
    def collection(self):
        if self._collection is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self.settings.vector_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.settings.vector_path), settings=ChromaSettings(anonymized_telemetry=False),
            )
            collection = self._client.get_or_create_collection(
                name="hotel_training", embedding_function=None,
                metadata={"hnsw:space": "cosine", "embedding_model": self.settings.embedding_model,
                          "dimensions": self.settings.embedding_dimensions},
            )
            metadata = collection.metadata or {}
            if (metadata.get("embedding_model") != self.settings.embedding_model
                    or metadata.get("dimensions") != self.settings.embedding_dimensions):
                raise ServiceError("O índice usa outro modelo ou dimensão. Configure um novo VECTOR_DB_PATH e reindexe os documentos.", 409)
            self._collection = collection
        return self._collection

    def replace_document(self, document_id: int, chunks: list[Chunk], embeddings: list[list[float]], metadata: dict) -> None:
        if not chunks or len(chunks) != len(embeddings):
            raise ServiceError("Quantidade de chunks e embeddings incompatível.")
        with self.lock:
            try:
                collection = self.collection
                generation = uuid4().hex
                collection.delete(where={"documento_id": document_id})
                for start in range(0, len(chunks), 100):
                    batch = chunks[start:start + 100]
                    collection.add(
                        ids=[f"{document_id}:{generation}:{start + i}" for i in range(len(batch))],
                        documents=[chunk.text for chunk in batch],
                        embeddings=embeddings[start:start + 100],
                        metadatas=[metadata | {"documento_id": document_id, "pagina": chunk.page, "secao": chunk.section}
                                   for chunk in batch],
                    )
            except ServiceError:
                raise
            except Exception as exc:
                logger.error("Falha ao atualizar índice: %s", type(exc).__name__)
                raise ServiceError("Não foi possível atualizar o índice vetorial.", 503) from None

    def remove_document(self, document_id: int) -> None:
        with self.lock:
            try:
                self.collection.delete(where={"documento_id": document_id})
            except ServiceError:
                raise
            except Exception as exc:
                logger.error("Falha ao remover índice: %s", type(exc).__name__)
                raise ServiceError("Não foi possível remover o documento do índice.", 503) from None

    def search(self, embedding: list[float], training_id: int, document_ids: list[int], top_k: int = 5) -> list[SearchHit]:
        if not document_ids:
            return []
        with self.lock:
            try:
                result = self.collection.query(
                    query_embeddings=[embedding], n_results=top_k,
                    where={"$and": [{"treinamento_id": training_id}, {"documento_id": {"$in": document_ids}}]},
                    include=["documents", "metadatas", "distances"],
                )
                return [SearchHit(text, metadata, distance) for text, metadata, distance in zip(
                    result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True
                )]
            except ServiceError:
                raise
            except Exception as exc:
                logger.error("Falha ao consultar índice: %s", type(exc).__name__)
                raise ServiceError("Não foi possível consultar o índice vetorial.", 503) from None
