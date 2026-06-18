"""Role definitions for the admin panel.

Single-tenant model: two roles backed by Django Groups.

- ADMIN    : full control — manage users, products, delete, activate, view everything.
- OPERATOR : point-of-sale staff — activate codes and view dashboards; no delete,
             no user management.

Superusers implicitly have all permissions.
"""

ADMIN = 'Admin'
OPERATOR = 'Operator'

ALL_ROLES = [ADMIN, OPERATOR]


def get_role(user):
    """Return the primary role string for a user, or None."""
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return ADMIN
    # Iterate groups.all() (not values_list) so a prefetch_related('groups')
    # cache is reused — avoids an extra query per user when serialising lists.
    names = {g.name for g in user.groups.all()}
    if ADMIN in names:
        return ADMIN
    if OPERATOR in names:
        return OPERATOR
    return None


def is_admin(user):
    return bool(user and user.is_authenticated and (user.is_superuser or get_role(user) == ADMIN))


def is_operator_or_admin(user):
    return get_role(user) in (ADMIN, OPERATOR)
