import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from app import runtime
from app.models import Documento, Treinamento
from app.services.errors import ServiceError
from app.services.ingest import stored_file_exists


@require_POST
def ask(request, training_id):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Sua sessão expirou. Entre novamente para continuar."}, status=401)
    training = get_object_or_404(Treinamento, pk=training_id, ativo=True)
    if request.content_type != "application/json":
        return JsonResponse({"detail": "Envie a pergunta em JSON."}, status=415)
    try:
        body = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"detail": "JSON inválido."}, status=422)
    if not isinstance(body, dict) or set(body) != {"pergunta"} or not isinstance(body["pergunta"], str):
        return JsonResponse({"detail": "Informe somente o campo pergunta."}, status=422)
    question = body["pergunta"].strip()
    if not 1 <= len(question) <= 2000:
        return JsonResponse({"detail": "A pergunta deve ter entre 1 e 2000 caracteres."}, status=422)
    with runtime.document_lock:
        indexed = Documento.objects.filter(treinamento=training, processado=True).only("pk", "caminho")
        ids = [
            document.pk for document in indexed
            if stored_file_exists(settings.SERVICE_SETTINGS.documents_path, document.caminho)
        ]
        if not ids:
            raise ServiceError(
                "Os materiais deste treinamento ainda não estão disponíveis para o assistente. "
                "Peça ao responsável para verificar a indexação dos documentos.",
                409,
            )
        with runtime.services() as (_, rag):
            return JsonResponse(rag.answer(question, training.pk, ids))


