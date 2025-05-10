from django.db import models

class Lote(models.Model):
    def __str__(self):
        return self.nombre

    nombre = models.CharField(max_length=255, unique=True)

    

class ArchivoLote(models.Model):
    def __str__(self):
        return self.nombre
    TIPO_CHOICES = [
        ('cosecha', 'Cosecha'),
        ('suelo', 'Análisis de Suelo'),
    ]

    nombre = models.CharField(max_length=255)
    lote = models.ForeignKey(Lote, on_delete=models.CASCADE, related_name='archivos')
    archivo = models.FileField(upload_to='lotes/')
    extension = models.CharField(max_length=20)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)  # ⬅️ nuevo
    fecha_carga = models.DateTimeField(auto_now_add=True)