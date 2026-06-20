from django.urls import path
from . import views

urlpatterns = [
    path('verify/<uuid:product_id>/', views.verify_product, name='verify-product'),
    path('check/<uuid:product_id>/', views.check_product, name='check-product'),
    path('scans/', views.scan_list, name='scan-list'),
    path('scans/export/', views.scan_export, name='scan-export'),
    path('scans/<int:scan_id>/', views.scan_detail, name='scan-detail'),
    path('stats/', views.dashboard_stats, name='dashboard-stats'),
    path('fraud-alerts/', views.fraud_alerts, name='fraud-alerts'),
    path('customers/', views.customer_list, name='customer-list'),
    path('customers/export/', views.customer_export, name='customer-export'),
    path('customers/<str:email>/', views.customer_detail, name='customer-detail'),
]
