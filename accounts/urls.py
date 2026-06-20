from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('auth/me/', views.me_view, name='me'),
    path('auth/change-password/', views.change_password_view, name='change-password'),
    path('auth/2fa/setup/', views.twofactor_setup, name='2fa-setup'),
    path('auth/2fa/enable/', views.twofactor_enable, name='2fa-enable'),
    path('auth/2fa/disable/', views.twofactor_disable, name='2fa-disable'),
    path('users/', views.user_list_create, name='user-list-create'),
    path('users/<int:user_id>/', views.user_detail, name='user-detail'),
    path('config/', views.site_config, name='site-config'),
    path('audit/', views.audit_list, name='audit-list'),
]
