from django.db import models

class Dataset(models.Model):
    id_dataset = models.AutoField(primary_key=True)
    id_usuario = models.IntegerField()
    nombre = models.CharField(max_length=255)
    fecha_creacion = models.DateTimeField()

    class Meta:
        db_table = 'dataset'
        managed = False
