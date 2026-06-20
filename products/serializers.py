from rest_framework import serializers
from .models import CatalogProduct, Product


class CatalogProductSerializer(serializers.ModelSerializer):
    unit_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CatalogProduct
        fields = [
            'id', 'name', 'brand', 'description', 'is_active',
            'unit_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProductListSerializer(serializers.ModelSerializer):
    scan_count = serializers.IntegerField(read_only=True)
    is_suspicious = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    activated_by_username = serializers.CharField(
        source='activated_by.username', read_only=True, default=None
    )

    class Meta:
        model = Product
        fields = [
            'id', 'catalog', 'product_name', 'brand', 'batch_number',
            'manufactured_date', 'qr_code_image', 'is_active',
            'status', 'status_display', 'activated_at', 'activated_by_username',
            'scan_count', 'is_suspicious', 'created_at', 'updated_at',
        ]
        read_only_fields = ['status', 'activated_at']


class ProductCreateSerializer(serializers.ModelSerializer):
    # A catalog product may be selected; its name/brand are then copied onto the unit.
    catalog = serializers.PrimaryKeyRelatedField(
        queryset=CatalogProduct.objects.all(), required=False, allow_null=True
    )
    product_name = serializers.CharField(required=False)

    class Meta:
        model = Product
        fields = [
            'id', 'catalog', 'product_name', 'brand', 'batch_number',
            'manufactured_date', 'is_active',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        catalog = attrs.get('catalog')
        if catalog:
            # Selecting a catalog product fills the name/brand from it.
            attrs['product_name'] = catalog.name
            attrs['brand'] = catalog.brand
        elif not attrs.get('product_name') and not self.instance:
            raise serializers.ValidationError(
                {'catalog': 'Select a product from the catalog (or provide product_name).'}
            )
        return attrs


class ProductDetailSerializer(serializers.ModelSerializer):
    scan_count = serializers.IntegerField(read_only=True)
    is_suspicious = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    activated_by_username = serializers.CharField(
        source='activated_by.username', read_only=True, default=None
    )
    scan_records = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'catalog', 'product_name', 'brand', 'batch_number',
            'manufactured_date', 'qr_code_image', 'is_active',
            'status', 'status_display', 'activated_at', 'activated_by_username',
            'scan_count', 'is_suspicious', 'scan_records',
            'created_at', 'updated_at',
        ]

    def get_scan_records(self, obj):
        from authentication.serializers import ScanRecordSerializer
        # select_related('product') so the serializer's product_* fields don't
        # fire one query per scan row. Pass context through so PII masking for
        # operators applies here too.
        records = obj.scan_records.select_related('product').all()
        return ScanRecordSerializer(records, many=True, context=self.context).data
