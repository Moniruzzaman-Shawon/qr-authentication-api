from rest_framework import serializers

from accounts.roles import is_admin
from .models import ScanRecord


def mask_email(email):
    """'john@email.com' -> 'j***@email.com' (privacy for non-admin viewers)."""
    if not email or '@' not in email:
        return 'hidden'
    local, _, domain = email.partition('@')
    return f"{(local[0] if local else '*')}***@{domain}"


class ScanRecordSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_brand = serializers.CharField(source='product.brand', read_only=True)
    product_batch = serializers.CharField(source='product.batch_number', read_only=True)
    product_status = serializers.CharField(source='product.status', read_only=True)
    alert_type = serializers.SerializerMethodField()

    class Meta:
        model = ScanRecord
        fields = [
            'id', 'product', 'product_name', 'product_brand', 'product_batch',
            'product_status', 'alert_type',
            'customer_email', 'customer_name', 'customer_phone',
            'ip_address', 'user_agent',
            'is_first_scan', 'scanned_at',
        ]

    def get_alert_type(self, obj):
        """Classify a scan for the fraud feed.

        - genuine           : the legitimate first scan
        - duplicate         : scanned again after a genuine scan exists
        - before_activation : scanned while PRINTED or after a recall (no genuine scan)
        """
        if obj.is_first_scan:
            return 'genuine'
        has_genuine = getattr(obj, 'product_has_genuine', None)
        if has_genuine is False:
            return 'before_activation'
        return 'duplicate'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Least privilege: operators (non-admins) don't get raw customer PII.
        request = self.context.get('request')
        if request and request.user.is_authenticated and not is_admin(request.user):
            data['customer_email'] = mask_email(data.get('customer_email'))
            data['customer_phone'] = ''
            data['ip_address'] = None
            data['user_agent'] = ''
        return data


class VerifyRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
