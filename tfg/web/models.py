from django.db import models

class Dataset(models.Model):
    id_dataset = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    created_at = models.DateField()

    class Meta:
        db_table = 'dataset'
        managed = False
