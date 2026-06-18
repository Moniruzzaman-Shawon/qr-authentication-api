from django.db import models
from django.db.models import Q
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
    is_first_scan = models.BooleanField(default=False)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scanned_at']
        indexes = [
            # customer_email is grouped/filtered by the customer endpoints;
            # the composite supports the "latest scan per customer" subquery.
            models.Index(fields=['customer_email', '-scanned_at']),
            # is_first_scan + scanned_at back the dashboard/fraud listings.
            models.Index(fields=['is_first_scan', '-scanned_at']),
        ]
        constraints = [
            # A product can have at most one genuine (first) scan — this is the
            # database-level guarantee that backs the "one-time QR" promise and
            # makes concurrent verification races impossible.
            models.UniqueConstraint(
                fields=['product'],
                condition=Q(is_first_scan=True),
                name='unique_first_scan_per_product',
            ),
        ]

    def __str__(self):
        status = "GENUINE" if self.is_first_scan else "SUSPICIOUS"
        return f"[{status}] {self.product.product_name} by {self.customer_email}"
