from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.pagination import StandardPagination
from .models import AuditLog, FailedLogin, SiteConfig, TwoFactor, log_action
from .permissions import IsAdmin
from .serializers import (
    AuditLogSerializer,
    RoleTokenObtainPairSerializer,
    SiteConfigSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


@api_view(['GET', 'PATCH'])
@permission_classes([AllowAny])
def site_config(request):
    """Public GET (the SPA reads branding); admin-only PATCH to update it."""
    config = SiteConfig.load()
    if request.method == 'GET':
        return Response(SiteConfigSerializer(config).data)

    from .roles import is_admin
    if not (request.user.is_authenticated and is_admin(request.user)):
        return Response({'detail': 'Admin role required.'}, status=status.HTTP_403_FORBIDDEN)
    serializer = SiteConfigSerializer(config, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        log_action(request, 'config.update', target='Site settings')
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAdmin])
def audit_list(request):
    logs = AuditLog.objects.all()
    paginator = StandardPagination()
    page = paginator.paginate_queryset(logs, request)
    return paginator.get_paginated_response(AuditLogSerializer(page, many=True).data)


def _client_ip(request):
    fwd = request.META.get('HTTP_X_FORWARDED_FOR')
    return fwd.split(',')[0].strip() if fwd else request.META.get('REMOTE_ADDR')


def _lockout_state(username):
    """Return (locked, retry_minutes) for a username based on recent failures."""
    import math
    from datetime import timedelta
    from django.utils import timezone
    from django.conf import settings as dj
    if not username:
        return False, 0
    window = timezone.now() - timedelta(minutes=dj.LOGIN_LOCKOUT_MINUTES)
    recent = FailedLogin.objects.filter(
        username__iexact=username, created_at__gte=window
    ).order_by('created_at')
    if recent.count() >= dj.LOGIN_MAX_ATTEMPTS:
        unlock_at = recent.first().created_at + timedelta(minutes=dj.LOGIN_LOCKOUT_MINUTES)
        retry = max(1, math.ceil((unlock_at - timezone.now()).total_seconds() / 60))
        return True, retry
    return False, 0


class LoginView(TokenObtainPairView):
    """POST {username, password, otp?} -> {access, refresh, user}.

    Adds brute-force lockout: after LOGIN_MAX_ATTEMPTS failures a username is
    locked for LOGIN_LOCKOUT_MINUTES.
    """

    serializer_class = RoleTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        from rest_framework.exceptions import APIException
        username = request.data.get('username', '')

        locked, retry = _lockout_state(username)
        if locked:
            return Response(
                {'detail': f'Account locked after too many failed attempts. '
                           f'Try again in {retry} minute(s).'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            response = super().post(request, *args, **kwargs)
        except APIException:
            FailedLogin.objects.create(username=username[:150], ip_address=_client_ip(request))
            raise

        # Success — clear the failure history for this username.
        FailedLogin.objects.filter(username__iexact=username).delete()
        return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def twofactor_setup(request):
    """Generate (or reuse) a pending TOTP secret and return its provisioning URI."""
    import pyotp
    tf, _ = TwoFactor.objects.get_or_create(
        user=request.user, defaults={'secret': pyotp.random_base32()}
    )
    if tf.enabled:
        return Response({'detail': 'Two-factor is already enabled.'},
                        status=status.HTTP_400_BAD_REQUEST)
    issuer = SiteConfig.load().app_name
    uri = pyotp.TOTP(tf.secret).provisioning_uri(name=request.user.username, issuer_name=issuer)
    return Response({'secret': tf.secret, 'otpauth_uri': uri})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def twofactor_enable(request):
    """Confirm a TOTP code to switch two-factor on."""
    import pyotp
    code = (request.data.get('code') or '').strip()
    try:
        tf = request.user.two_factor
    except TwoFactor.DoesNotExist:
        return Response({'detail': 'Run setup first.'}, status=status.HTTP_400_BAD_REQUEST)
    if not pyotp.TOTP(tf.secret).verify(code, valid_window=1):
        return Response({'code': 'Invalid code.'}, status=status.HTTP_400_BAD_REQUEST)
    tf.enabled = True
    tf.save(update_fields=['enabled'])
    log_action(request, 'security.2fa_enable', target=request.user.username)
    return Response({'detail': 'Two-factor enabled.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def twofactor_disable(request):
    """Disable two-factor after confirming the current password."""
    password = request.data.get('password') or ''
    if not request.user.check_password(password):
        return Response({'password': 'Password is incorrect.'},
                        status=status.HTTP_400_BAD_REQUEST)
    TwoFactor.objects.filter(user=request.user).delete()
    log_action(request, 'security.2fa_disable', target=request.user.username)
    return Response({'detail': 'Two-factor disabled.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """Blacklist the supplied refresh token."""
    token = request.data.get('refresh')
    if not token:
        return Response({'detail': 'refresh token required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        RefreshToken(token).blacklist()
    except TokenError:
        return Response({'detail': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_205_RESET_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    return Response(UserSerializer(request.user).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    """Let the signed-in user change their own password.

    Body: {current_password, new_password}. The current password must match,
    and the new one is run through Django's password validators.
    """
    current = request.data.get('current_password') or ''
    new = request.data.get('new_password') or ''
    user = request.user

    if not user.check_password(current):
        return Response(
            {'current_password': 'Current password is incorrect.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        validate_password(new, user)
    except DjangoValidationError as exc:
        return Response({'new_password': list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new)
    user.save(update_fields=['password'])
    return Response({'detail': 'Password updated successfully.'})


@api_view(['GET', 'POST'])
@permission_classes([IsAdmin])
def user_list_create(request):
    if request.method == 'GET':
        # prefetch groups so UserSerializer.get_role doesn't query per user.
        users = User.objects.prefetch_related('groups').order_by('username')
        return Response(UserSerializer(users, many=True).data)

    serializer = UserCreateSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        log_action(request, 'user.create', target=user.username,
                   detail=f'role={request.data.get("role", "")}')
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAdmin])
def user_detail(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(UserSerializer(user).data)

    if request.method == 'PATCH':
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(request, 'user.update', target=user.username,
                       detail=', '.join(request.data.keys()))
            return Response(UserSerializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # DELETE -> soft-deactivate rather than destroy (preserves audit trail).
    if user == request.user:
        return Response(
            {'detail': 'You cannot deactivate your own account.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user.is_active = False
    user.save(update_fields=['is_active'])
    log_action(request, 'user.deactivate', target=user.username)
    return Response(status=status.HTTP_204_NO_CONTENT)
