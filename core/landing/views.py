import pandas as pd, numpy as np, geopandas as gpd, json, time, os
from pyproj import Transformer
from scipy.interpolate import griddata
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from shapely.geometry import Point, Polygon
from .models import ArchivoLote, Lote
from django.contrib import messages



def home(request):
    return render(request, "index.html")

def mapa_view(request):
    return render(request, 'mapa.html')

def cargar_archivos(request):
    import os
    import tempfile
    import geopandas as gpd
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    lotes = Lote.objects.all().order_by('nombre')

    if request.method == 'POST':
        lote_nombre = request.POST.get('lote')

        if not lote_nombre:
            messages.error(request, "O nome do lote é obrigatório.")
            return redirect('cargar_archivos')

        lote_obj = get_object_or_404(Lote, nombre=lote_nombre)
        archivos = request.FILES.getlist('archivos')

        if not archivos:
            messages.error(request, "É necessário enviar ao menos um arquivo.")
            return redirect('cargar_archivos')

        # → Agrupar archivos por nombre base (para .shp/.dbf/.shx)
        conjuntos = {}
        for archivo in archivos:
            base = archivo.name.split('.')[0]
            if base not in conjuntos:
                conjuntos[base] = []
            conjuntos[base].append(archivo)

        for base, archivos_shp in conjuntos.items():
            tmpdir = tempfile.mkdtemp()
            ruta_geojson = None

            for archivo in archivos_shp:
                nombre = archivo.name
                extension = nombre.split('.')[-1].lower()
                tipo = request.POST.get('tipo') or 'cosecha'
                ruta_destino = os.path.join(tmpdir, nombre)

                with open(ruta_destino, 'wb+') as destino:
                    for chunk in archivo.chunks():
                        destino.write(chunk)

                # Guardar cada archivo tal cual
                ArchivoLote.objects.create(
                    lote=lote_obj,
                    nombre=nombre,
                    archivo=archivo,
                    extension=extension,
                    tipo=tipo
                )

            # Intentar cargar shapefile y convertir a GeoJSON
            try:
                shp_file = next((f.name for f in archivos_shp if f.name.endswith('.shp')), None)
                if shp_file:
                    full_path = os.path.join(tmpdir, shp_file)
                    gdf = gpd.read_file(full_path)
                    geojson_str = gdf.to_json()

                    geojson_filename = f"{base}.geojson"
                    path_geojson = default_storage.save(f"lotes/{geojson_filename}", ContentFile(geojson_str.encode('utf-8')))

                    ArchivoLote.objects.create(
                        lote=lote_obj,
                        nombre=geojson_filename,
                        archivo=path_geojson,
                        extension='geojson',
                        tipo=tipo
                    )
            except Exception as e:
                print(f"⚠️ Error al convertir {base} a GeoJSON: {e}")

        messages.success(request, f"Lote '{lote_nombre}' carregado com sucesso.")
        return redirect('cargar_archivos')

    return render(request, 'upload.html', {'lotes': lotes})

def mapa_shapefile(request):
    lotes = Lote.objects.all().order_by('nombre')

    print("📦 Lotes disponibles:", list(lotes))  

    return render(request, "mapa_shapefile.html", {
        "lotes": lotes,
    })


def get_capas_lote(request):
    lote_id = request.GET.get('lote_id')
    print(f"🔍 Lote ID recibido: {lote_id}")

    try:
        archivos = ArchivoLote.objects.filter(lote_id=lote_id)
    except Exception as e:
        print(f"❌ Error al filtrar archivos: {e}")
        return JsonResponse({"error": "Error interno del servidor."}, status=500)

    print(f"📦 Archivos encontrados: {archivos.count()}")

    resultado = []
    for archivo in archivos:
        print(f" - {archivo.nombre} ({archivo.tipo})")
        resultado.append({
            "nombre": archivo.nombre,
            "url": archivo.archivo.url,
            "extension": archivo.extension,
            "tipo": archivo.tipo,
            "fecha": archivo.fecha_carga.strftime('%Y-%m-%d %H:%M'),
        })

    return JsonResponse({"capas": resultado})


def get_capa_tipo(request):
    lote_id = request.GET.get('lote_id')
    tipo = request.GET.get('tipo')

    print(f"🛰️ Petición de capa tipo: lote_id={lote_id}, tipo={tipo}")

    archivos = ArchivoLote.objects.filter(lote_id=lote_id, tipo=tipo, extension='geojson').order_by('-fecha_carga')

    print(f"🔎 Archivos encontrados: {archivos.count()}")
    resultado = []

    # Paletas de colores por tipo
    paletas = {
        'cosecha': ["#00FF00", "#66FF00", "#CCFF00", "#FFFF00", "#FFCC00",
                    "#FF9900", "#FF6600", "#FF3300", "#FF0000", "#990000"],
        'nitrogeno': ["#08306b", "#08519c", "#2171b5", "#4292c6", "#6baed6",
                      "#9ecae1", "#c6dbef", "#deebf7", "#f7fbff", "#ffffff"],
        'fosforo': ["#3f007d", "#54278f", "#6a51a3", "#807dba", "#9e9ac8",
                    "#bcbddc", "#dadaeb", "#efedf5", "#f2f0f7", "#ffffff"],
        'fertilizante': ["#ffffe5", "#fff7bc", "#fee391", "#fec44f", "#fe9929",
                         "#ec7014", "#cc4c02", "#993404", "#662506", "#4d2600"]
    }

    leyenda = []
    estadisticas = {}

    # Solo procesamos el último archivo (puede adaptarse si querés todos)
    if archivos.exists():
        archivo = archivos.first()
        print(f"📂 Procesando archivo: {archivo.nombre}")
        try:
            gdf = gpd.read_file(archivo.archivo.path)

            if 'rate' in gdf.columns:
                min_rate = gdf['rate'].min()
                max_rate = gdf['rate'].max()
                print(f"📊 Rango 'rate': {min_rate} a {max_rate}")

                if tipo == 'cosecha':
                    valores_validos = gdf['rate'].dropna()
                    if not valores_validos.empty:
                        estadisticas = {
                            'min': round(valores_validos.min(), 2),
                            'max': round(valores_validos.max(), 2),
                            'prom': round(valores_validos.mean(), 2)
                        }

                bins = np.linspace(min_rate, max_rate, 11)
                etiquetas = [f"{int(bins[i])} - {int(bins[i+1])}" for i in range(10)]
                colores = paletas.get(tipo, ['#999999'] * 10)

                leyenda = [{"rango": r, "color": c} for r, c in zip(etiquetas, colores)]
                print(f"🎨 Leyenda armada: {len(leyenda)} clases")

            else:
                leyenda = [{"rango": "Sin datos", "color": "#000000"}]
                print("⚠️ No hay columna 'rate'. Leyenda mínima agregada.")

        except Exception as e:
            print("💥 Error al leer archivo para leyenda:", str(e))
            leyenda = []

    # Respuesta JSON con archivos + leyenda
    for archivo in archivos:
        resultado.append({
            'nombre': archivo.nombre,
            'url': archivo.archivo.url,
            'extension': archivo.extension,
            'fecha': archivo.fecha_carga.strftime('%Y-%m-%d %H:%M'),
        })

    return JsonResponse({
        'capas': resultado,
        'leyenda': leyenda,
        'estadisticas': estadisticas
    })






def mapa_geopackage(request):
    inicio = time.time()
    print("📥 Cargando CSV...")
    df = pd.read_csv("staticfiles/archivoscsv/archivos.csv")
    df['Latitud'] = df['Latitud'].astype(str).str.replace(',', '.').astype(float)
    df['Longitud'] = df['Longitud'].astype(str).str.replace(',', '.').astype(float)

    # Conversión a coordenadas UTM
    transformer = Transformer.from_crs("epsg:4326", "epsg:32722", always_xy=True)
    df[['x', 'y']] = df.apply(
        lambda row: pd.Series(transformer.transform(row['Longitud'], row['Latitud'])),
        axis=1
    )

    x = df['x'].values
    y = df['y'].values
    z = df['Rendimiento (kg/ha)'].values

    print("🧱 Generando grilla...")
    resolucion = 5
    grid_x, grid_y = np.mgrid[
        x.min():x.max():complex(0, int((x.max() - x.min()) // resolucion)),
        y.min():y.max():complex(0, int((y.max() - y.min()) // resolucion))
    ]

    print("📈 Interpolando...")
    z_interp = griddata((x, y), z, (grid_x, grid_y), method='linear')

    print("🌐 Generando GeoJSON...")
    features = []

    step_x = (grid_x[1][0] - grid_x[0][0]) / 2
    step_y = (grid_y[0][1] - grid_y[0][0]) / 2

    for i in range(grid_x.shape[0]):
        for j in range(grid_x.shape[1]):
            value = z_interp[i][j]
            if np.isnan(value):
                continue

            gx, gy = grid_x[i][j], grid_y[i][j]
            corners_utm = [
                (gx - step_x, gy - step_y),
                (gx + step_x, gy - step_y),
                (gx + step_x, gy + step_y),
                (gx - step_x, gy + step_y),
                (gx - step_x, gy - step_y)
            ]
            corners_geo = [
                transformer.transform(px, py, direction='INVERSE')
                for px, py in corners_utm
            ]

            color = get_color_by_rinde(value)

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [corners_geo]
                },
                "properties": {
                    "rinde": round(value, 2),
                    "color": color
                }
            }
            features.append(feature)

    geojson_data = {
        "type": "FeatureCollection",
        "features": features
    }

    fin = time.time()
    print(f"✅ GeoJSON generado con {len(features)} zonas")
    print(f"🕒 Tiempo total de procesamiento: {fin - inicio:.2f} segundos")

    # Enviar al template
    context = {
        'geojson_data': geojson_data
    }
    return render(request, 'mapa_geopackage.html', context)

# def cargar_archivos(request):
#     archivos = request.FILES.getlist('arquivos')
#     ruta = "staticfiles/arch_externos"
    
#     for archivo in archivos:
#         destino = open(f"{ruta}/{archivo.name}", 'wb')
#         destino.write(archivo.read())
#         destino.close()

#     return render(request, "upload.html")









    
def data_capa(request):
    tipo = request.GET.get('tipo')
    print("📥 GET recibido con tipo =", tipo)

    # 🔍 Buscar el último archivo que contenga el tipo en su nombre
    archivo_obj = ArchivoLote.objects.filter(nombre__icontains=tipo).order_by('-fecha_carga').first()

    if not archivo_obj:
        print("❌ No se encontró archivo con tipo:", tipo)
        return JsonResponse({'error': f"Arquivo para tipo '{tipo}' não encontrado."}, status=404)

    ruta = archivo_obj.archivo.path
    print("📂 Ruta archivo BD:", ruta)

    try:
        gdf = gpd.read_file(ruta)
        print("✅ Archivo leído. Columnas:", list(gdf.columns))

        # 🎨 Paletas por tipo
        paletas = {
            'cosecha': ["#00FF00", "#66FF00", "#CCFF00", "#FFFF00", "#FFCC00",
                        "#FF9900", "#FF6600", "#FF3300", "#FF0000", "#990000"],
            'nitrogeno': ["#08306b", "#08519c", "#2171b5", "#4292c6", "#6baed6",
                          "#9ecae1", "#c6dbef", "#deebf7", "#f7fbff", "#ffffff"],
            'fosforo': ["#3f007d", "#54278f", "#6a51a3", "#807dba", "#9e9ac8",
                        "#bcbddc", "#dadaeb", "#efedf5", "#f2f0f7", "#ffffff"],
            'fertilizante': ["#ffffe5", "#fff7bc", "#fee391", "#fec44f", "#fe9929",
                             "#ec7014", "#cc4c02", "#993404", "#662506", "#4d2600"]
        }

        leyenda = []
        estadisticas = {}

        if 'rate' in gdf.columns:
            min_rate = gdf['rate'].min()
            max_rate = gdf['rate'].max()
            print(f"📊 Rango de 'rate': {min_rate} a {max_rate}")

            # 🧮 Estadísticas SOLO para cosecha
            if tipo == "cosecha":
                valores_validos = gdf['rate'].dropna()
                if not valores_validos.empty:
                    estadisticas = {
                        'min': round(valores_validos.min(), 2),
                        'max': round(valores_validos.max(), 2),
                        'prom': round(valores_validos.mean(), 2)
                    }
                    print(f"📈 Estadísticas cosecha → Min: {estadisticas['min']} | Max: {estadisticas['max']} | Prom: {estadisticas['prom']}")

            # 🎨 Clasificación por color
            bins = np.linspace(min_rate, max_rate, 11)
            etiquetas = [f"{int(bins[i])} - {int(bins[i+1])}" for i in range(10)]
            colores = paletas.get(tipo, ['#999999'] * 10)

            gdf['rango'] = pd.cut(gdf['rate'], bins=bins, labels=etiquetas, include_lowest=True)
            mapa_colores = dict(zip(etiquetas, colores))
            gdf['color'] = gdf['rango'].map(mapa_colores)

            leyenda = [{"rango": r, "color": c} for r, c in mapa_colores.items()]
            print(f"🎨 Leyenda generada con {len(leyenda)} clases")

        else:
            gdf['color'] = '#000000'
            gdf['rango'] = 'Sin datos'
            leyenda = [{"rango": "Sin datos", "color": "#000000"}]
            print("⚠️ No se encontró 'rate'. Se asignó color negro.")

        geojson_dict = json.loads(gdf.to_json())

        return JsonResponse({
            "geojson": geojson_dict,
            "leyenda": leyenda,
            "estadisticas": estadisticas
        })

    except Exception as e:
        print("💥 Error al procesar:", str(e))
        return JsonResponse({'error': str(e)}, status=500)


def datos_shapefile(request):
    carpeta = "staticfiles/arch_externos"
    shp_file = next((f for f in os.listdir(carpeta) if f.endswith(".shp")), None)

    if not shp_file:
        return JsonResponse({"error": "No se encontró shapefile"}, status=404)

    ruta = os.path.join(carpeta, shp_file)

    try:
        gdf = gpd.read_file(ruta)

        # Clasificación como ya tenías
        min_rate = gdf['rate'].min()
        max_rate = gdf['rate'].max()
        bins = np.linspace(min_rate, max_rate, 11)
        etiquetas = [f"{int(bins[i])} - {int(bins[i+1])}" for i in range(10)]
        colores = ["#00FF00", "#66FF00", "#CCFF00", "#FFFF00", "#FFCC00",
                   "#FF9900", "#FF6600", "#FF3300", "#FF0000", "#990000"]
        gdf['rango'] = pd.cut(gdf['rate'], bins=bins, labels=etiquetas, include_lowest=True)
        mapa_colores = dict(zip(etiquetas, colores))
        gdf['color'] = gdf['rango'].map(mapa_colores)

        # Convertir a GeoJSON como dict
        geojson_dict = json.loads(gdf.to_json())
        return JsonResponse(geojson_dict)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
def get_color_by_rinde(value):
    if value < 2900:
        return '#ff0000'
    elif value < 3500:
        return '#fde725'  # amarillo
    elif value < 4500:
        return '#35b779'
    else:
        return '#ff0000'  # rojo

def datos_mapa(request):
    inicio = time.time()

    print(" Cargando CSV...")
    df = pd.read_csv("staticfiles/archivoscsv/muestra_2ha.csv")

    df['Latitud'] = df['Latitud'].astype(str).str.replace(',', '.').astype(float)
    df['Longitud'] = df['Longitud'].astype(str).str.replace(',', '.').astype(float)

    transformer = Transformer.from_crs("epsg:4326", "epsg:32722", always_xy=True)
    df[['x', 'y']] = df.apply(lambda row: pd.Series(transformer.transform(row['Longitud'], row['Latitud'])), axis=1)

    x = df['x'].values
    y = df['y'].values
    z = df['Rendimiento (kg/ha)'].values

    print(" Generando grilla...")
    resolucion = 1
    grid_x, grid_y = np.mgrid[
        x.min():x.max():complex(0, int((x.max() - x.min()) // resolucion)),
        y.min():y.max():complex(0, int((y.max() - y.min()) // resolucion))
    ]

    print("Interpolando...")
    z_interp = griddata((x, y), z, (grid_x, grid_y), method='linear')

    print("🌐 Generando GeoJSON...")
    features = []

    step_x = (grid_x[1][0] - grid_x[0][0]) / 2
    step_y = (grid_y[0][1] - grid_y[0][0]) / 2

    for i in range(grid_x.shape[0]):
        for j in range(grid_x.shape[1]):
            value = z_interp[i][j]
            if np.isnan(value):
                continue

            gx, gy = grid_x[i][j], grid_y[i][j]
            corners_utm = [
                (gx - step_x, gy - step_y),
                (gx + step_x, gy - step_y),
                (gx + step_x, gy + step_y),
                (gx - step_x, gy + step_y),
                (gx - step_x, gy - step_y)
            ]
            corners_geo = [transformer.transform(px, py, direction='INVERSE') for px, py in corners_utm]
            color = get_color_by_rinde(value)

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [corners_geo]
                },
                "properties": {
                    "rinde": round(value, 2),
                    "color": color
                }
            }
            features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    fin = time.time()

    print(f"✅ GeoJSON generado con {len(features)} zonas")
    print(f"🕒 Tiempo total de procesamiento: {fin - inicio:.2f} segundos")

    return JsonResponse(geojson)
   
def generar_capa(variable, archivo="staticfiles/archivoscsv/nutrientes.csv"):
    print(f"📥 Cargando datos de {variable}...")
    df = pd.read_csv(archivo)

    df['Latitud'] = df['Latitud'].astype(str).str.replace(',', '.').astype(float)
    df['Longitud'] = df['Longitud'].astype(str).str.replace(',', '.').astype(float)

    transformer = Transformer.from_crs("epsg:4326", "epsg:32722", always_xy=True)
    df[['x', 'y']] = df.apply(lambda row: pd.Series(transformer.transform(row['Longitud'], row['Latitud'])), axis=1)

    x = df['x'].values
    y = df['y'].values
    z = df[variable].values

    grid_x, grid_y = np.mgrid[x.min():x.max():30j, y.min():y.max():30j]
    z_interp = griddata((x, y), z, (grid_x, grid_y), method='linear')

    step_x = (grid_x[1][0] - grid_x[0][0]) / 2
    step_y = (grid_y[0][1] - grid_y[0][0]) / 2

    features = []
    for i in range(grid_x.shape[0]):
        for j in range(grid_x.shape[1]):
            value = z_interp[i][j]
            if np.isnan(value):
                continue
            gx, gy = grid_x[i][j], grid_y[i][j]
            corners_utm = [
                (gx - step_x, gy - step_y),
                (gx + step_x, gy - step_y),
                (gx + step_x, gy + step_y),
                (gx - step_x, gy + step_y),
                (gx - step_x, gy - step_y)
            ]
            corners_geo = [transformer.transform(px, py, direction='INVERSE') for px, py in corners_utm]

            color = '#999999'

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [corners_geo]
                },
                "properties": {
                    "valor": round(value, 2),
                    "color": color
                }
            }
            features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    print(f"✅ GeoJSON de {variable} generado con {len(features)} zonas")
    return JsonResponse(geojson)

def capa_fosforo(request):
    return generar_capa("P(ppm)")

def capa_potasio(request):
    return generar_capa("K(ppm)")

def capa_nitrogeno(request):
    return generar_capa("N(ppm)")

def capa_azufre(request):
    return generar_capa("S(ppm)")

def capa_ph(request):
    return generar_capa("pH")

def capa_compactacion(request):
    return generar_capa("Compactacion(MPa)")

# def mapa_geopackage(request):
#     inicio = time.time()
#     print("📥 Cargando CSV...")
#     df = pd.read_csv("staticfiles/archivoscsv/archivos.csv")
#     df['Latitud'] = df['Latitud'].astype(str).str.replace(',', '.').astype(float)
#     df['Longitud'] = df['Longitud'].astype(str).str.replace(',', '.').astype(float)

#     # Conversión a coordenadas UTM
#     transformer = Transformer.from_crs("epsg:4326", "epsg:32722", always_xy=True)
#     df[['x', 'y']] = df.apply(
#         lambda row: pd.Series(transformer.transform(row['Longitud'], row['Latitud'])),
#         axis=1
#     )

#     x = df['x'].values
#     y = df['y'].values
#     z = df['Rendimiento (kg/ha)'].values

#     print("🧱 Generando grilla...")
#     resolucion = 5
#     grid_x, grid_y = np.mgrid[
#         x.min():x.max():complex(0, int((x.max() - x.min()) // resolucion)),
#         y.min():y.max():complex(0, int((y.max() - y.min()) // resolucion))
#     ]

#     print("📈 Interpolando...")
#     z_interp = griddata((x, y), z, (grid_x, grid_y), method='linear')

#     print("🌐 Generando GeoJSON...")
#     features = []

#     step_x = (grid_x[1][0] - grid_x[0][0]) / 2
#     step_y = (grid_y[0][1] - grid_y[0][0]) / 2

#     for i in range(grid_x.shape[0]):
#         for j in range(grid_x.shape[1]):
#             value = z_interp[i][j]
#             if np.isnan(value):
#                 continue

#             gx, gy = grid_x[i][j], grid_y[i][j]
#             corners_utm = [
#                 (gx - step_x, gy - step_y),
#                 (gx + step_x, gy - step_y),
#                 (gx + step_x, gy + step_y),
#                 (gx - step_x, gy + step_y),
#                 (gx - step_x, gy - step_y)
#             ]
#             corners_geo = [
#                 transformer.transform(px, py, direction='INVERSE')
#                 for px, py in corners_utm
#             ]

#             color = get_color_by_rinde(value)

#             feature = {
#                 "type": "Feature",
#                 "geometry": {
#                     "type": "Polygon",
#                     "coordinates": [corners_geo]
#                 },
#                 "properties": {
#                     "rinde": round(value, 2),
#                     "color": color
#                 }
#             }
#             features.append(feature)

#     geojson_data = {
#         "type": "FeatureCollection",
#         "features": features
#     }

#     fin = time.time()
#     print(f"✅ GeoJSON generado con {len(features)} zonas")
#     print(f"🕒 Tiempo total de procesamiento: {fin - inicio:.2f} segundos")

#     # Enviar al template
#     context = {
#         'geojson_data': geojson_data
#     }
#     return render(request, 'mapa_geopackage.html', context)

