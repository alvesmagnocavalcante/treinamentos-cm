from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.models import Documento, Treinamento
from app.routes.training import DB

router = APIRouter()


class Question(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    pergunta: str = Field(min_length=1, max_length=2000)


@router.post("/treinamentos/{training_id}/perguntar")
def ask(training_id: int, body: Question, request: Request, session: DB):
    training = session.get(Treinamento, training_id)
    if training is None or not training.ativo:
        raise HTTPException(404, "Treinamento não encontrado.")
    with request.app.state.document_lock:
        document_ids = list(session.scalars(select(Documento.id).where(
            Documento.treinamento_id == training_id, Documento.processado.is_(True),
        )))
        return request.app.state.rag.answer(body.pergunta, training_id, document_ids)
