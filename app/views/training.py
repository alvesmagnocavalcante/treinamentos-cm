from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from app.models import Aula, Documento, Setor, Treinamento
from app.services.video import normalize_video_url


@login_required
@require_GET
def index(request):
    trainings = Treinamento.objects.filter(ativo=True).order_by("titulo")
    sectors = Setor.objects.prefetch_related(Prefetch("treinamentos", queryset=trainings, to_attr="disponiveis"))
    return render(request, "index.html", {"setores": sectors}, using="jinja2")


@login_required
@require_GET
def training(request, training_id):
    training = get_object_or_404(
        Treinamento.objects.filter(ativo=True).select_related("setor").prefetch_related(
            Prefetch("documentos", queryset=Documento.objects.defer("arquivo"), to_attr="materiais"),
            Prefetch("aulas", queryset=Aula.objects.filter(ativo=True).order_by("ordem", "pk"), to_attr="publicadas"),
        ), pk=training_id,
    )
    selected = request.GET.get("aula")
    if selected:
        lesson = next((item for item in training.publicadas if str(item.pk) == selected), None)
    else:
        lesson = next(iter(training.publicadas), None)
    if selected and lesson is None:
        raise Http404("Aula não encontrada neste treinamento.")
    has_video = bool(lesson and normalize_video_url(lesson.video_url))
    return render(request, "treinamento.html", {
        "treinamento": training, "aula_atual": lesson, "has_video": has_video,
    }, using="jinja2")


