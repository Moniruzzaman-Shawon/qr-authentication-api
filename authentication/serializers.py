from rest_framework import serializers
from .models import ScanRecord


class ScanRecordSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_brand = serializers.CharField(source='product.brand', read_only=True)
    product_batch = serializers.CharField(source='product.batch_number', read_only=True)

    class Meta:
        model = ScanRecord
        fields = [
            'id', 'product', 'product_name', 'product_brand', 'product_batch',
            'customer_email', 'customer_name', 'customer_phone',
            'ip_address', 'user_agent',
            'is_first_scan', 'scanned_at',
        ]


class VerifyRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
