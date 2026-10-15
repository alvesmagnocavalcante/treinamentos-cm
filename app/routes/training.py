from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import ROOT
from app.database import get_session
from app.models import Setor, Treinamento

router = APIRouter()
templates = Jinja2Templates(directory=str(ROOT / "app/templates"))
DB = Annotated[Session, Depends(get_session)]


@router.get("/")
def index(request: Request, session: DB):
    setores = session.scalars(
        select(Setor).options(selectinload(Setor.treinamentos)).order_by(Setor.nome)
    ).all()
    return templates.TemplateResponse(request=request, name="index.html", context={"setores": setores})


@router.get("/admin")
def admin(request: Request, session: DB):
    setores = session.scalars(select(Setor).order_by(Setor.nome)).all()
    treinamentos = session.scalars(select(Treinamento).options(selectinload(Treinamento.setor)).order_by(Treinamento.titulo)).all()
    return templates.TemplateResponse(request=request, name="admin.html", context={"setores": setores, "treinamentos": treinamentos})


@router.post("/admin/setores")
def create_sector(
    session: DB,
    nome: Annotated[str, Form(min_length=1, max_length=100)],
    descricao: Annotated[str, Form(max_length=5000)] = "",
):
    nome = nome.strip()
    if not nome:
        raise HTTPException(422, "Informe o nome do setor.")
    session.add(Setor(nome=nome, descricao=descricao.strip()))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Já existe um setor com esse nome.") from None
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/treinamentos")
def create_training(
    session: DB,
    setor_id: Annotated[int, Form(gt=0)],
    titulo: Annotated[str, Form(min_length=1, max_length=200)],
    descricao: Annotated[str, Form(max_length=5000)] = "",
    conteudo: Annotated[str, Form(max_length=100000)] = "",
    ativo: Annotated[bool, Form()] = False,
):
    titulo = titulo.strip()
    if not titulo:
        raise HTTPException(422, "Informe o título do treinamento.")
    if session.get(Setor, setor_id) is None:
        raise HTTPException(404, "Setor não encontrado.")
    treinamento = Treinamento(
        setor_id=setor_id, titulo=titulo, descricao=descricao.strip(),
        conteudo=conteudo.strip(), ativo=ativo,
    )
    session.add(treinamento)
    session.commit()
    return RedirectResponse("/" if not ativo else f"/treinamentos/{treinamento.id}", status_code=303)


@router.get("/treinamentos/{treinamento_id}")
def training(treinamento_id: int, request: Request, session: DB):
    treinamento = session.scalar(
        select(Treinamento).where(Treinamento.id == treinamento_id, Treinamento.ativo.is_(True))
        .options(selectinload(Treinamento.documentos), selectinload(Treinamento.setor))
    )
    if treinamento is None:
        raise HTTPException(404, "Treinamento não encontrado.")
    return templates.TemplateResponse(
        request=request, name="treinamento.html", context={"treinamento": treinamento}
    )
