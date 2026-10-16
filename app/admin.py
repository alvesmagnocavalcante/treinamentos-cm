from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from app.models import Aula, Documento, Setor, Treinamento

admin.site.site_header = "Carmel · Administração"
admin.site.site_title = "Carmel Hotéis"
admin.site.index_title = "Gestão dos treinamentos"


@admin.register(Setor)
class SetorAdmin(admin.ModelAdmin):
    list_display = ("nome", "descricao")
    search_fields = ("nome",)


class AulaInline(admin.TabularInline):
    model = Aula
    fields = ("ordem", "titulo", "video_url", "ativo")
    extra = 0
    show_change_link = True


@admin.register(Treinamento)
class TreinamentoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "setor", "ativo", "gerenciar_documentos", "abrir_treinamento")
    list_filter = ("setor", "ativo")
    search_fields = ("titulo", "descricao")
    inlines = [AulaInline]
    readonly_fields = ("gerenciar_documentos", "abrir_treinamento")

    @admin.display(description="Documentos / RAG")
    def gerenciar_documentos(self, obj):
        if not obj or not obj.pk:
            return "Salve o treinamento para enviar documentos."
        return format_html('<a href="{}">Gerenciar documentos</a>', reverse("training_documents", args=[obj.pk]))

    @admin.display(description="Área do colaborador")
    def abrir_treinamento(self, obj):
        if not obj or not obj.pk or not obj.ativo:
            return "Treinamento indisponível."
        return format_html('<a href="{}">Abrir treinamento</a>', reverse("training", args=[obj.pk]))


@admin.register(Aula)
class AulaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "treinamento", "ordem", "ativo")
    list_filter = ("ativo", "treinamento__setor")
    list_select_related = ("treinamento",)
    search_fields = ("titulo", "treinamento__titulo")
    fields = ("treinamento", "ordem", "titulo", "video_url", "conteudo", "ativo")


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "treinamento", "tipo", "processado", "criado_em")
    list_filter = ("processado", "tipo")
    search_fields = ("nome", "treinamento__titulo")
    fields = ("treinamento", "nome", "tipo", "processado", "criado_em", "gerenciar")
    readonly_fields = fields
    list_select_related = ("treinamento",)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Exclusões passam pelo serviço que remove arquivo e vetores.
        return False

    @admin.display(description="Ações")
    def gerenciar(self, obj):
        return format_html('<a href="{}">Gerenciar documentos deste treinamento</a>', reverse("training_documents", args=[obj.treinamento_id]))
