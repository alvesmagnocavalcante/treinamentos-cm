import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select

from app.models import Documento, Treinamento
from app.routes.training import DB, templates
from app.services.errors import ServiceError
from app.services.ingest import save_upload, stored_path

router = APIRouter()
logger = logging.getLogger(__name__)


def require_training(training_id: int, session) -> Treinamento:
    training = session.get(Treinamento, training_id)
    if training is None:
        raise HTTPException(404, "Treinamento não encontrado.")
    return training


def require_document(document_id: int, session) -> Documento:
    document = session.get(Documento, document_id)
    if document is None:
        raise HTTPException(404, "Documento não encontrado.")
    return document


def render_documents(request: Request, session, training: Treinamento, error=None, status=200):
    documents = session.scalars(select(Documento).where(Documento.treinamento_id == training.id).order_by(Documento.id)).all()
    return templates.TemplateResponse(request=request, name="admin_documentos.html", status_code=status, context={
        "treinamento": training, "documentos": documents, "erro": error,
        "max_upload_mb": request.app.state.settings.max_upload_bytes // (1024 * 1024),
    })


@router.get("/admin/treinamentos/{training_id}/documentos")
def documents(training_id: int, request: Request, session: DB):
    return render_documents(request, session, require_training(training_id, session))


@router.post("/admin/treinamentos/{training_id}/documentos")
def upload_document(training_id: int, request: Request, session: DB, arquivo: Annotated[UploadFile, File()]):
    training = require_training(training_id, session)
    settings = request.app.state.settings
    path = None
    saved = False
    try:
        with request.app.state.document_lock:
            path, name = save_upload(arquivo, settings.documents_path, settings.max_upload_bytes)
            document = Documento(treinamento_id=training.id, nome=name, caminho=path.name, tipo=path.suffix[1:])
            session.add(document)
            session.commit()
            saved = True
            count = request.app.state.documents.index(document, session)
            logger.info("Documento %s indexado: %s chunks", document.id, count)
    except ServiceError as exc:
        if path and not saved:
            path.unlink(missing_ok=True)
        logger.warning("Upload/indexação falhou: HTTP %s", exc.status_code)
        return render_documents(request, session, training, str(exc), exc.status_code)
    except Exception:
        if path and not saved:
            path.unlink(missing_ok=True)
        raise
    finally:
        arquivo.file.close()
    return RedirectResponse(f"/admin/treinamentos/{training_id}/documentos", status_code=303)


@router.post("/admin/documentos/{document_id}/reindexar")
def reindex(document_id: int, request: Request, session: DB):
    with request.app.state.document_lock:
        document = require_document(document_id, session)
        try:
            request.app.state.documents.index(document, session)
        except ServiceError as exc:
            return render_documents(request, session, document.treinamento, str(exc), exc.status_code)
        return RedirectResponse(f"/admin/treinamentos/{document.treinamento_id}/documentos", status_code=303)


@router.post("/admin/documentos/{document_id}/excluir")
def delete(document_id: int, request: Request, session: DB):
    with request.app.state.document_lock:
        document = require_document(document_id, session)
        training_id = document.treinamento_id
        try:
            request.app.state.documents.delete(document, session)
        except ServiceError as exc:
            return render_documents(request, session, document.treinamento, str(exc), exc.status_code)
        return RedirectResponse(f"/admin/treinamentos/{training_id}/documentos", status_code=303)


@router.get("/documentos/{document_id}/arquivo")
def download(document_id: int, request: Request, session: DB):
    document = require_document(document_id, session)
    if not document.treinamento.ativo:
        raise HTTPException(404, "Documento não encontrado.")
    path = stored_path(request.app.state.settings.documents_path, document.caminho)
    media = "application/pdf" if document.tipo == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, filename=document.nome, media_type=media)
