import math
import re

import httpx

from app.config import Settings
from app.services.errors import ServiceError
from app.services.http import post_json


class EmbeddingService:
    def __init__(self, settings: Settings, client: httpx.Client):
        self.settings = settings
        self.client = client
        self.model = "models/" + settings.embedding_model.removeprefix("models/")
        if not re.fullmatch(r"models/[\w.-]+", self.model):
            raise ValueError("GEMINI_EMBEDDING_MODEL inválido.")

    def embed_text(self, texto: str) -> list[float]:
        return self._embed([texto], "RETRIEVAL_QUERY")[0]

    def embed_documents(self, textos: list[str]) -> list[list[float]]:
        return self._embed(textos, "RETRIEVAL_DOCUMENT")

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        if not texts:
            return []
        if not self.settings.google_api_key:
            raise ServiceError("Configure GOOGLE_API_KEY para indexar e consultar documentos.", 503)
        vectors = []
        for start in range(0, len(texts), 32):
            batch = texts[start:start + 32]
            payload = post_json(
                self.client, "Gemini", f"https://generativelanguage.googleapis.com/v1beta/{self.model}:batchEmbedContents",
                headers={"x-goog-api-key": self.settings.google_api_key},
                json={"requests": [
                    {"model": self.model, "content": {"parts": [{"text": text}]},
                     "taskType": task, "outputDimensionality": self.settings.embedding_dimensions}
                    for text in batch
                ]},
            )
            try:
                embeddings = payload["embeddings"]
                if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                    raise ValueError
                for embedding in embeddings:
                    vector = embedding["values"]
                    if not isinstance(vector, list) or len(vector) != self.settings.embedding_dimensions:
                        raise ValueError
                    if any(type(v) not in (int, float) or not math.isfinite(v) for v in vector):
                        raise ValueError
                    norm = math.sqrt(sum(v * v for v in vector))
                    if norm == 0:
                        raise ValueError
                    vectors.append([v / norm for v in vector])
            except (KeyError, TypeError, ValueError, OverflowError):
                raise ServiceError("Gemini retornou embeddings inválidos.") from None
        return vectors
