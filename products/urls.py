from django.urls import path
from . import views

urlpatterns = [
    path('catalog/', views.catalog_list_create, name='catalog-list-create'),
    path('catalog/<int:catalog_id>/', views.catalog_detail, name='catalog-detail'),
    path('products/', views.product_list_create, name='product-list-create'),
    path('products/bulk-create/', views.bulk_create_products, name='bulk-create'),
    path('products/bulk-csv/', views.bulk_create_csv, name='bulk-csv'),
    path('products/bulk-activate/', views.bulk_activate_products, name='bulk-activate'),
    path('products/download-qr/', views.download_qr_codes, name='download-qr'),
    path('products/download-qr-pdf/', views.download_qr_pdf, name='download-qr-pdf'),
    path('products/export/', views.product_export, name='product-export'),
    path('products/<uuid:product_id>/', views.product_detail, name='product-detail'),
    path('products/<uuid:product_id>/activate/', views.activate_product, name='activate'),
]
