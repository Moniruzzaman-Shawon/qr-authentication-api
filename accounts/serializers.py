from django.contrib.auth.models import Group, User
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AuditLog, SiteConfig
from .roles import ADMIN, ALL_ROLES, get_role


class SiteConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteConfig
        fields = ['app_name', 'tagline', 'company_name', 'support_email',
                  'accent_color', 'updated_at']
        read_only_fields = ['updated_at']


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['id', 'username', 'action', 'target', 'detail', 'created_at']


class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Issue JWTs and embed the user's role + profile in the response.

    If the user has TOTP two-factor enabled, a valid `otp` code is required.
    """

    def validate(self, attrs):
        data = super().validate(attrs)  # authenticates username/password

        tf = getattr(self.user, 'two_factor', None)
        if tf and tf.enabled:
            import pyotp
            otp = (self.initial_data.get('otp') or '').strip()
            if not otp:
                raise serializers.ValidationError(
                    {'otp': 'Two-factor code required.', 'otp_required': True}
                )
            if not pyotp.TOTP(tf.secret).verify(otp, valid_window=1):
                raise serializers.ValidationError({'otp': 'Invalid two-factor code.'})

        data['user'] = UserSerializer(self.user).data
        return data


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    two_factor_enabled = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'two_factor_enabled', 'is_active', 'last_login', 'date_joined',
        ]
        read_only_fields = ['id', 'last_login', 'date_joined']

    def get_role(self, obj):
        return get_role(obj)

    def get_two_factor_enabled(self, obj):
        tf = getattr(obj, 'two_factor', None)
        return bool(tf and tf.enabled)


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=ALL_ROLES)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'password', 'role', 'is_active',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        role = validated_data.pop('role')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        # Admins get staff access to the Django admin too.
        user.is_staff = role == ADMIN
        user.save()
        _assign_role(user, role)
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, required=False)
    role = serializers.ChoiceField(choices=ALL_ROLES, required=False)

    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name',
            'password', 'role', 'is_active',
        ]

    def update(self, instance, validated_data):
        role = validated_data.pop('role', None)
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        if role is not None:
            instance.is_staff = role == ADMIN
            _assign_role(instance, role)
        instance.save()
        return instance


def _assign_role(user, role):
    """Make `role` the user's sole role group."""
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.set([group])
