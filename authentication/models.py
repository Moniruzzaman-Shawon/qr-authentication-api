from django.db import models
from products.models import Product


class ScanRecord(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='scan_records'
    )
    customer_email = models.EmailField()
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    is_first_scan = models.BooleanField(default=False)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scanned_at']

    def __str__(self):
        status = "GENUINE" if self.is_first_scan else "SUSPICIOUS"
        return f"[{status}] {self.product.product_name} by {self.customer_email}"
