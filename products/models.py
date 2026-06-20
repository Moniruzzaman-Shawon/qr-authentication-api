import uuid
from django.conf import settings
from django.db import models


class CatalogProduct(models.Model):
    """A named product in the admin's catalog (e.g. "Engine Oil 5W-30").

    The admin curates these; QR-coded units (Product) are generated against a
    chosen catalog entry so the name is selected, never re-typed.
    """
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    @property
    def unit_count(self):
        if hasattr(self, '_unit_count'):
            return self._unit_count
        return self.units.count()

    def __str__(self):
        return f"{self.name} ({self.brand})"


class Product(models.Model):
    # Two-phase activation lifecycle.
    STATUS_PRINTED = 'printed'    # created at factory, not yet for sale
    STATUS_ACTIVE = 'active'      # activated at point of sale, ready for customer
    STATUS_VERIFIED = 'verified'  # customer scanned once -> genuine recorded
    STATUS_FLAGGED = 'flagged'    # scanned again after verify -> suspicious
    STATUS_CHOICES = [
        (STATUS_PRINTED, 'Printed'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_VERIFIED, 'Verified'),
        (STATUS_FLAGGED, 'Flagged'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalog = models.ForeignKey(
        CatalogProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='units',
    )
    # Denormalised copies taken from the catalog at creation time (kept so
    # verification and historical records stay stable even if the catalog changes).
    product_name = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, blank=True, default='')
    batch_number = models.CharField(max_length=100)
    manufactured_date = models.DateField()
    qr_code_image = models.ImageField(upload_to='qr_codes/', blank=True, null=True)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PRINTED, db_index=True
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activated_products',
    )

    # Admin kill-switch: a deactivated product can never verify as genuine (recall).
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def scan_count(self):
        # Prefer an annotated value (set by list querysets) to avoid N+1 COUNT queries.
        if hasattr(self, '_scan_count'):
            return self._scan_count
        return self.scan_records.count()

    @property
    def is_suspicious(self):
        return self.status == self.STATUS_FLAGGED or self.scan_count > 1

    def __str__(self):
        return f"{self.product_name} - {self.batch_number}"
