import json
import logging

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.db.models import Exists, OuterRef, Prefetch
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from app import runtime
from app.forms import DocumentUploadForm
from app.models import Aula, Documento, Setor, Treinamento
from app.services.errors import ServiceError
from app.services.ingest import save_upload, stored_path
from app.services.video import video_preview_url

logger = logging.getLogger(__name__)


def document_available(document):
    try:
        stored_path(settings.SERVICE_SETTINGS.documents_path, document.caminho)
    except ServiceError:
        return False
    return True


@login_required
@require_GET
def index(request):
    videos = Aula.objects.filter(treinamento_id=OuterRef("pk"), ativo=True).exclude(video_url="")
    trainings = Treinamento.objects.filter(ativo=True).annotate(tem_video=Exists(videos)).order_by("titulo")
    sectors = Setor.objects.prefetch_related(Prefetch("treinamentos", queryset=trainings, to_attr="disponiveis"))
    return render(request, "index.html", {"setores": sectors}, using="jinja2")


@login_required
@require_GET
def training(request, training_id):
    training = get_object_or_404(
        Treinamento.objects.filter(ativo=True).select_related("setor").prefetch_related(
            Prefetch("documentos", to_attr="materiais"),
            Prefetch("aulas", queryset=Aula.objects.filter(ativo=True).order_by("ordem", "pk"), to_attr="publicadas"),
        ), pk=training_id,
    )
    selected = request.GET.get("aula")
    lesson = next((item for item in training.publicadas if str(item.pk) == selected), None) if selected else next(iter(training.publicadas), None)
    if selected and lesson is None:
        raise Http404("Aula não encontrada neste treinamento.")
    training.materiais = [document for document in training.materiais if document_available(document)]
    preview = video_preview_url(lesson.video_url) if lesson else ""
    return render(request, "treinamento.html", {"treinamento": training, "aula_atual": lesson, "video_preview_url": preview}, using="jinja2")


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
    with runtime.document_lock, runtime.services() as (_, rag):
        indexed = Documento.objects.filter(treinamento=training, processado=True).only("pk", "caminho")
        ids = [document.pk for document in indexed if document_available(document)]
        return JsonResponse(rag.answer(question, training.pk, ids))


def render_documents(request, training, error=None, status=200):
    documents = list(training.documentos.all())
    for document in documents:
        document.arquivo_disponivel = document_available(document)
    return render(request, "admin_documentos.html", {
        "treinamento": training, "documentos": documents, "erro": error,
        "max_upload_mb": settings.SERVICE_SETTINGS.max_upload_bytes // (1024 * 1024),
        "pode_enviar": request.user.has_perm("app.add_documento"),
        "pode_reindexar": request.user.has_perm("app.change_documento"),
        "pode_excluir": request.user.has_perm("app.delete_documento"),
    }, status=status, using="jinja2")


@staff_member_required
@permission_required("app.view_documento", raise_exception=True)
@require_http_methods(["GET", "POST"])
def documents(request, training_id):
    training = get_object_or_404(Treinamento.objects.select_related("setor"), pk=training_id)
    if request.method == "GET":
        return render_documents(request, training)
    if not request.user.has_perm("app.add_documento"):
        raise PermissionDenied
    form = DocumentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return render_documents(request, training, "Selecione um documento PDF ou DOCX.", 422)
    path = None
    saved = False
    try:
        with runtime.document_lock:
            config = settings.SERVICE_SETTINGS
            path, name = save_upload(form.cleaned_data["arquivo"], config.documents_path, config.max_upload_bytes)
            document = Documento.objects.create(treinamento=training, nome=name, caminho=path.name, tipo=path.suffix[1:])
            saved = True
            with runtime.services() as (service, _):
                count = service.index(document)
            logger.info("Documento %s indexado: %s chunks", document.pk, count)
    except ServiceError as exc:
        response = render_documents(request, training, str(exc), exc.status_code)
        if exc.retry_after is not None:
            response["Retry-After"] = str(exc.retry_after)
        return response
    finally:
        if path is not None and not saved:
            path.unlink(missing_ok=True)
    return redirect("training_documents", training_id=training.pk)


@staff_member_required
@permission_required("app.change_documento", raise_exception=True)
@require_POST
def reindex(request, document_id):
    with runtime.document_lock:
        document = get_object_or_404(Documento.objects.select_related("treinamento__setor"), pk=document_id)
        try:
            with runtime.services() as (service, _):
                service.index(document)
        except ServiceError as exc:
            return render_documents(request, document.treinamento, str(exc), exc.status_code)
    return redirect("training_documents", training_id=document.treinamento_id)


@staff_member_required
@permission_required("app.delete_documento", raise_exception=True)
@require_POST
def delete_document(request, document_id):
    with runtime.document_lock:
        document = get_object_or_404(Documento.objects.select_related("treinamento"), pk=document_id)
        training_id = document.treinamento_id
        try:
            with runtime.services() as (service, _):
                service.delete(document)
        except ServiceError as exc:
            return render_documents(request, document.treinamento, str(exc), exc.status_code)
    return redirect("training_documents", training_id=training_id)


@login_required
@require_GET
def download(request, document_id):
    document = get_object_or_404(Documento.objects.select_related("treinamento"), pk=document_id)
    if not document.treinamento.ativo and not request.user.has_perm("app.view_documento"):
        raise Http404("Documento não encontrado.")
    path = stored_path(settings.SERVICE_SETTINGS.documents_path, document.caminho)
    media = "application/pdf" if document.tipo == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path.open("rb"), as_attachment=True, filename=document.nome, content_type=media)
