from django.contrib.admin import AdminSite
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse


class TrainingAdminSite(AdminSite):
    index_template = "admin/dashboard.html"

    def index(self, request, extra_context=None):
        from app.models import Aula, Documento, Setor, Treinamento

        def can_view(model):
            name = model._meta.model_name
            return request.user.has_perm(f"app.view_{name}") or request.user.has_perm(f"app.change_{name}")

        metrics = []
        for model, label, field, detail in (
            (Setor, "Setores", None, ""),
            (Treinamento, "Treinamentos", "ativo", "Ativos"),
            (Aula, "Aulas", "ativo", "Publicadas"),
            (Documento, "Documentos", "processado", "Indexados"),
        ):
            if not can_view(model):
                continue
            aggregates = {"total": Count("pk")}
            if field:
                aggregates["ready"] = Count("pk", filter=Q(**{field: True}))
            counts = model.objects.aggregate(**aggregates)
            metrics.append({
                "label": label, "total": counts["total"], "ready": counts.get("ready"),
                "detail": detail, "url": reverse(f"admin:app_{model._meta.model_name}_changelist"),
            })

        query = request.GET.get("q", "").strip()[:200]
        status = request.GET.get("status", "")
        if status not in {"active", "inactive"}:
            status = ""
        trainings = None
        if can_view(Treinamento):
            trainings = Treinamento.objects.select_related("setor").order_by("titulo", "pk")
            if query:
                trainings = trainings.filter(Q(titulo__icontains=query) | Q(setor__nome__icontains=query))
            if status:
                trainings = trainings.filter(ativo=status == "active")
            trainings = Paginator(trainings, 20).get_page(request.GET.get("page"))

        context = {
            **(extra_context or {}), "title": "Painel de administração", "metrics": metrics,
            "trainings_page": trainings, "search_query": query, "status_filter": status,
            "can_add_training": request.user.has_perm("app.add_treinamento"),
            "can_change_training": request.user.has_perm("app.change_treinamento"),
            "can_view_documents": request.user.has_perm("app.view_documento"),
        }
        return super().index(request, extra_context=context)
