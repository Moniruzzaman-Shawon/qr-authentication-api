from rest_framework.permissions import BasePermission

from .roles import is_admin, is_operator_or_admin


class IsAdmin(BasePermission):
    """Full-access admin role (or superuser)."""

    message = 'Admin role required.'

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsAdminOrOperator(BasePermission):
    """Admin or Operator role. Operators can activate codes and read dashboards."""

    message = 'Admin or Operator role required.'

    def has_permission(self, request, view):
        return is_operator_or_admin(request.user)
