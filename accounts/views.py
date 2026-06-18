from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .permissions import IsAdmin
from .serializers import (
    RoleTokenObtainPairSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


class LoginView(TokenObtainPairView):
    """POST {username, password} -> {access, refresh, user}."""

    serializer_class = RoleTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


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
    return Response(status=status.HTTP_204_NO_CONTENT)
