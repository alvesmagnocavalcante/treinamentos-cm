from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from app.services.errors import ServiceError
from app.services.video import normalize_video_url


class Setor(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True, max_length=5000)

    class Meta:
        ordering = ["nome"]
        verbose_name_plural = "setores"
        constraints = [models.CheckConstraint(condition=~models.Q(nome=""), name="setor_nome_preenchido")]

    def clean(self):
        self.nome = self.nome.strip()
        if not self.nome:
            raise ValidationError({"nome": "Informe o nome do setor."})

    def __str__(self):
        return self.nome


class Treinamento(models.Model):
    setor = models.ForeignKey(Setor, on_delete=models.PROTECT, related_name="treinamentos")
    titulo = models.CharField("título", max_length=200)
    descricao = models.TextField("descrição", blank=True, max_length=5000)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["titulo"]
        constraints = [models.CheckConstraint(condition=~models.Q(titulo=""), name="treinamento_titulo_preenchido")]

    def clean(self):
        self.titulo = self.titulo.strip()
        if not self.titulo:
            raise ValidationError({"titulo": "Informe o título do treinamento."})

    def __str__(self):
        return self.titulo


class Aula(models.Model):
    treinamento = models.ForeignKey(Treinamento, on_delete=models.CASCADE, related_name="aulas")
    titulo = models.CharField("título", max_length=200)
    ordem = models.PositiveSmallIntegerField(default=1)
    video_url = models.URLField("vídeo no Google Drive", max_length=2048, blank=True)
    conteudo = models.TextField("explicação", blank=True, max_length=100000)
    ativo = models.BooleanField("publicada", default=True)

    class Meta:
        ordering = ["ordem", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["treinamento", "ordem"], name="aula_ordem_por_treinamento"),
            models.CheckConstraint(condition=models.Q(ordem__gte=1), name="aula_ordem_positiva"),
            models.CheckConstraint(condition=~models.Q(titulo=""), name="aula_titulo_preenchido"),
        ]

    def clean(self):
        self.titulo = self.titulo.strip()
        if not self.titulo:
            raise ValidationError({"titulo": "Informe o título da aula."})
        try:
            self.video_url = normalize_video_url(self.video_url)
        except ServiceError as exc:
            raise ValidationError({"video_url": str(exc)}) from None

    def __str__(self):
        return f"{self.ordem}. {self.titulo}"


class Documento(models.Model):
    treinamento = models.ForeignKey(Treinamento, on_delete=models.PROTECT, related_name="documentos")
    nome = models.CharField(max_length=255)
    caminho = models.CharField(max_length=255)
    tipo = models.CharField(max_length=4, choices=[("pdf", "PDF"), ("docx", "DOCX")])
    processado = models.BooleanField("indexado", default=False)
    criado_em = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["pk"]
        constraints = [models.CheckConstraint(condition=models.Q(tipo__in=["pdf", "docx"]), name="documento_tipo_suportado")]

    def __str__(self):
        return self.nome
