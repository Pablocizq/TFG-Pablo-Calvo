from django.db import models

class Dataset(models.Model):
    id_dataset = models.AutoField(primary_key=True)
    id_usuario = models.IntegerField()
    nombre = models.CharField(max_length=255)
    fecha_creacion = models.DateTimeField()
    identificador = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'dataset'
        managed = False

class Usuario(models.Model):
    id_usuario = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    correo = models.CharField(max_length=255, unique=True)
    contrasena = models.CharField(max_length=255)
    token_ckan = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'usuario'
        managed = False
