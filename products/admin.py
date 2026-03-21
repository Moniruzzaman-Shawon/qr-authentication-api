from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'product_name', 'brand', 'batch_number',
        'manufactured_date', 'is_active', 'scan_count',
        'is_suspicious', 'created_at',
    ]
    list_filter = ['is_active', 'brand', 'manufactured_date']
    search_fields = ['product_name', 'brand', 'batch_number']
    readonly_fields = ['id', 'created_at', 'updated_at', 'scan_count', 'is_suspicious']
