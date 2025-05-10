from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from landing.views import (
    home, datos_mapa, mapa_view, capa_fosforo, capa_potasio, capa_nitrogeno, capa_azufre, capa_ph, capa_compactacion, mapa_geopackage, 
    cargar_archivos, mapa_shapefile, datos_shapefile, data_capa, get_capas_lote, get_capa_tipo
    
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('mapa/', mapa_view, name='mapa'),
    path('datos-mapa/', datos_mapa, name='datos_mapa'),
    path('capa-fosforo/', capa_fosforo, name='capa_fosforo'),
    path('capa-potasio/', capa_potasio, name='capa_potasio'),
    path('capa-nitrogeno/', capa_nitrogeno, name='capa_nitrogeno'),
    path('capa-azufre/', capa_azufre, name='capa_azufre'),
    path('capa-ph/', capa_ph, name='capa_ph'),
    path('capa-compactacion/', capa_compactacion, name='capa_compactacion'),
    path('mapa-geopckage/', mapa_geopackage, name='mapa-geopackage'),
    #path('upload/', upload, name='upload'),
    path('cargar_archivos/', cargar_archivos, name='cargar_archivos'),
    path('mapa-shapefile/', mapa_shapefile, name='mapa_shapefile'),
    path('datos-shapefile/', datos_shapefile, name='datos_shapefile'),
    path('data-capa/', data_capa, name='data_capa'),
    path('get_capas_lote/', get_capas_lote, name='get_capas_lote'),
    path('get_capa_tipo/', get_capa_tipo, name='get_capa_tipo'),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)