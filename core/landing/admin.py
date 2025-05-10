from django.contrib import admin
from .models import ArchivoLote, Lote

@admin.register(ArchivoLote)
class ArchivoLoteAdmin(admin.ModelAdmin):
    list_display = ('lote', 'archivo', 'extension', 'fecha_carga')
    search_fields = ('lote__nombre',)

@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ('nombre',)  # ← corregido con coma final
    search_fields = ('nombre',)
