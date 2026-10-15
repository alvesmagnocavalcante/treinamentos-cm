from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Setor(Base):
    __tablename__ = "setores"
    __table_args__ = (CheckConstraint("length(trim(nome)) > 0"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), unique=True)
    descricao: Mapped[str] = mapped_column(Text, default="")
    treinamentos: Mapped[list["Treinamento"]] = relationship(back_populates="setor")


class Treinamento(Base):
    __tablename__ = "treinamentos"
    __table_args__ = (CheckConstraint("length(trim(titulo)) > 0"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    setor_id: Mapped[int] = mapped_column(ForeignKey("setores.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text, default="")
    conteudo: Mapped[str] = mapped_column(Text, default="")
    ativo: Mapped[bool] = mapped_column(default=True)
    setor: Mapped[Setor] = relationship(back_populates="treinamentos")
    documentos: Mapped[list["Documento"]] = relationship(
        back_populates="treinamento", order_by="Documento.id"
    )


class Documento(Base):
    __tablename__ = "documentos"
    __table_args__ = (CheckConstraint("tipo IN ('pdf', 'docx')"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    treinamento_id: Mapped[int] = mapped_column(ForeignKey("treinamentos.id"), index=True)
    nome: Mapped[str] = mapped_column(String(255))
    caminho: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(4))
    processado: Mapped[bool] = mapped_column(default=False)
    criado_em: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    treinamento: Mapped[Treinamento] = relationship(back_populates="documentos")
