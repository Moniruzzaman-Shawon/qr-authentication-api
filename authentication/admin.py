from django.contrib import admin
from .models import ScanRecord


@admin.register(ScanRecord)
class ScanRecordAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'customer_email', 'customer_name',
        'is_first_scan', 'ip_address', 'scanned_at',
    ]
    list_filter = ['is_first_scan', 'scanned_at']
    search_fields = [
        'customer_email', 'customer_name', 'customer_phone',
        'ip_address', 'product__product_name', 'product__batch_number',
    ]
    readonly_fields = ['scanned_at']
