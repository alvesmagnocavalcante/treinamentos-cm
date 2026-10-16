import math
from dataclasses import dataclass

from django.db import transaction
from pgvector.django import CosineDistance

from app.models import Documento, DocumentoTrecho
from app.services.errors import ServiceError


@dataclass(frozen=True)
class SearchHit:
    text: str
    metadata: dict
    distance: float


class VectorStore:
    """Textos e embeddings no mesmo banco dos treinamentos; busca exata por cosseno."""

    def __init__(self, settings):
        self.settings = settings

    def validate_vector(self, vector):
        if (len(vector) != self.settings.embedding_dimensions
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
                or not any(vector)):
            raise ServiceError("Embedding inválido ou com dimensão incompatível.", 422)

    def replace_document(self, document_id, chunks, embeddings, metadata):
        if not chunks or len(chunks) != len(embeddings):
            raise ServiceError("Quantidade de chunks e embeddings incompatível.", 422)
        for vector in embeddings:
            self.validate_vector(vector)
        with transaction.atomic():
            document = Documento.objects.select_for_update().only("treinamento_id").get(pk=document_id)
            if document.treinamento_id != metadata["treinamento_id"]:
                raise ServiceError("Documento não pertence ao treinamento informado.", 422)
            DocumentoTrecho.objects.filter(documento_id=document_id).delete()
            DocumentoTrecho.objects.bulk_create([
                DocumentoTrecho(documento_id=document_id, ordem=i, texto=chunk.text, pagina=chunk.page,
                               secao=chunk.section, embedding=vector, embedding_model=self.settings.embedding_model,
                               dimensions=self.settings.embedding_dimensions)
                for i, (chunk, vector) in enumerate(zip(chunks, embeddings, strict=True))
            ], batch_size=100)

    def search(self, embedding, training_id, document_ids, top_k=5):
        if not document_ids:
            return []
        self.validate_vector(embedding)
        chunks = DocumentoTrecho.objects.filter(documento__treinamento_id=training_id,
                                                documento_id__in=document_ids, documento__processado=True)
        if chunks.exclude(embedding_model=self.settings.embedding_model, dimensions=self.settings.embedding_dimensions).exists():
            raise ServiceError("Os documentos usam outro modelo ou dimensão. Reindexe os documentos do treinamento.", 409)
        nearest = chunks.annotate(distance=CosineDistance("embedding", embedding)).order_by("distance", "pk").select_related(
            "documento__treinamento__setor"
        ).defer("embedding", "documento__arquivo")[:top_k]
        return [SearchHit(chunk.texto, {
            "documento_id": chunk.documento_id, "documento": chunk.documento.nome,
            "treinamento_id": training_id, "setor": chunk.documento.treinamento.setor.nome,
            "pagina": chunk.pagina, "secao": chunk.secao,
        }, float(chunk.distance)) for chunk in nearest]
