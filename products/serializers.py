from rest_framework import serializers
from .models import Product


class ProductListSerializer(serializers.ModelSerializer):
    scan_count = serializers.IntegerField(read_only=True)
    is_suspicious = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'product_name', 'brand', 'batch_number',
            'manufactured_date', 'qr_code_image', 'is_active',
            'scan_count', 'is_suspicious', 'created_at', 'updated_at',
        ]


class ProductCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            'id', 'product_name', 'brand', 'batch_number',
            'manufactured_date', 'is_active',
        ]
        read_only_fields = ['id']


class ProductDetailSerializer(serializers.ModelSerializer):
    scan_count = serializers.IntegerField(read_only=True)
    is_suspicious = serializers.BooleanField(read_only=True)
    scan_records = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'product_name', 'brand', 'batch_number',
            'manufactured_date', 'qr_code_image', 'is_active',
            'scan_count', 'is_suspicious', 'scan_records',
            'created_at', 'updated_at',
        ]

    def get_scan_records(self, obj):
        from authentication.serializers import ScanRecordSerializer
        records = obj.scan_records.all()
        return ScanRecordSerializer(records, many=True).data
