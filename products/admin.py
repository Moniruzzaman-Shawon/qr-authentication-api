from django.contrib import admin
from .models import CatalogProduct, Product


@admin.register(CatalogProduct)
class CatalogProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'brand', 'is_active', 'unit_count', 'created_at']
    list_filter = ['is_active', 'brand']
    search_fields = ['name', 'brand']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'product_name', 'brand', 'batch_number', 'status',
        'manufactured_date', 'is_active', 'scan_count',
        'is_suspicious', 'created_at',
    ]
    list_filter = ['status', 'is_active', 'brand', 'manufactured_date']
    search_fields = ['product_name', 'brand', 'batch_number']
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'scan_count', 'is_suspicious',
        'activated_at', 'activated_by',
    ]
