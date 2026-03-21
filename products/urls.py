from django.urls import path
from . import views

urlpatterns = [
    path('products/', views.product_list_create, name='product-list-create'),
    path('products/<uuid:product_id>/', views.product_detail, name='product-detail'),
    path('products/bulk-create/', views.bulk_create_products, name='bulk-create'),
    path('products/bulk-csv/', views.bulk_create_csv, name='bulk-csv'),
    path('products/download-qr/', views.download_qr_codes, name='download-qr'),
]
