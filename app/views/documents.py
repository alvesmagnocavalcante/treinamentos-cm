from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from app import runtime
from app.forms import DocumentUploadForm
from app.models import Documento, Treinamento
from app.services.errors import ServiceError
from app.services.ingest import stored_file_exists, stored_path


def render_documents(request, training, error=None):
    documents = list(training.documentos.all())
    for document in documents:
        document.arquivo_disponivel = stored_file_exists(settings.SERVICE_SETTINGS.documents_path, document.caminho)
    response = render(request, "admin_documentos.html", {
        "treinamento": training, "documentos": documents, "erro": str(error) if error else None,
        "max_upload_mb": settings.SERVICE_SETTINGS.max_upload_bytes // (1024 * 1024),
        "pode_enviar": request.user.has_perm("app.add_documento"),
        "pode_reindexar": request.user.has_perm("app.change_documento"),
        "pode_excluir": request.user.has_perm("app.delete_documento"),
    }, status=error.status_code if error else 200, using="jinja2")
    if error is not None and error.retry_after is not None:
        response["Retry-After"] = str(error.retry_after)
    return response


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
        return render_documents(request, training, ServiceError("Selecione um documento PDF ou DOCX.", 422))
    try:
        with runtime.document_lock, runtime.services() as (service, _):
            document = service.upload(training, form.cleaned_data["arquivo"])
            service.index(document)
    except ServiceError as exc:
        return render_documents(request, training, exc)
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
            return render_documents(request, document.treinamento, exc)
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
            return render_documents(request, document.treinamento, exc)
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
