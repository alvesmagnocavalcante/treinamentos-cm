from contextlib import contextmanager
from threading import RLock

import httpx
from django.conf import settings

from app.services.documents import DocumentService
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService
from app.services.rag import RagService
from app.services.vector_store import VectorStore

document_lock = RLock()
store = VectorStore(settings.SERVICE_SETTINGS)


@contextmanager
def services():
    config = settings.SERVICE_SETTINGS
    with httpx.Client(timeout=config.timeout_seconds, follow_redirects=False) as client:
        embeddings = EmbeddingService(config, client)
        yield (
            DocumentService(config, embeddings, store),
            RagService(embeddings, store, LLMService(config, client), config.max_distance),
        )
