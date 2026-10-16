from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from app import runtime
from app.forms import DocumentUploadForm, DriveSyncForm
from app.models import Documento, Treinamento
from app.services.errors import ServiceError
from app.services.drive import DriveClient
from app.services.drive_sync import DriveSyncService
from app.services.document_files import document_path


def render_documents(request, training, error=None):
    documents = list(training.documentos.defer("arquivo"))
    response = render(request, "admin_documentos.html", {
        "treinamento": training, "documentos": documents, "erro": str(error) if error else None,
        "max_upload_mb": settings.SERVICE_SETTINGS.max_upload_bytes // (1024 * 1024),
        "pode_enviar": request.user.has_perm("app.add_documento"),
        "pode_reindexar": request.user.has_perm("app.change_documento"),
        "pode_excluir": request.user.has_perm("app.delete_documento"),
        "pode_sincronizar": request.user.has_perms(("app.add_documento", "app.change_documento", "app.change_treinamento")),
        "avisos": messages.get_messages(request),
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
@permission_required(("app.view_documento", "app.add_documento", "app.change_documento", "app.change_treinamento"), raise_exception=True)
@require_POST
def sync_drive(request, training_id):
    training = get_object_or_404(Treinamento.objects.select_related("setor"), pk=training_id)
    form = DriveSyncForm(request.POST)
    if not form.is_valid():
        return render_documents(request, training, ServiceError(str(form.errors["pasta"][0]), 422))
    try:
        with runtime.document_lock, runtime.services() as (service, _), DriveClient.connect(settings.SERVICE_SETTINGS) as drive:
            result = DriveSyncService(service, drive).sync(training, form.cleaned_data["pasta"])
    except ServiceError as exc:
        return render_documents(request, training, exc)
    messages.success(request, f"Drive sincronizado: {result.indexed} documento(s) indexado(s), {result.unchanged} sem alterações.")
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
    with document_path(document, settings.SERVICE_SETTINGS) as path:
        # A origem temporária é removida antes da resposta; o buffer pertence ao FileResponse.
        stream = BytesIO(path.read_bytes())
        media = "application/pdf" if path.suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    response = FileResponse(stream, as_attachment=True, filename=document.nome, content_type=media)
    response["Cache-Control"] = "private, no-store"
    return response
