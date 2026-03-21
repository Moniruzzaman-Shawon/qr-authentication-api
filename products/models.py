import uuid
from django.db import models


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_name = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, default='Rahman Trades Bangladesh')
    batch_number = models.CharField(max_length=100)
    manufactured_date = models.DateField()
    qr_code_image = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def scan_count(self):
        return self.scan_records.count()

    @property
    def is_suspicious(self):
        return self.scan_count > 1

    def __str__(self):
        return f"{self.product_name} - {self.batch_number}"
