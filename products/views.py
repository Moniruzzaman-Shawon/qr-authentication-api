import io
import zipfile
import qrcode
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAdmin, IsAdminOrOperator
from accounts.roles import is_admin
from core.pagination import StandardPagination
from .models import CatalogProduct, Product
from .qr import build_verify_url
from .serializers import (
    CatalogProductSerializer,
    ProductListSerializer,
    ProductCreateSerializer,
    ProductDetailSerializer,
)


def _product_qs():
    """Base queryset tuned for list/detail rendering.

    - annotate scan_count so each row doesn't fire its own COUNT
    - select_related the FKs the serializers traverse (activated_by.username,
      catalog) so a list of N products is a single query, not 1 + N.
    """
    return (
        Product.objects
        .select_related('activated_by', 'catalog')
        .annotate(_scan_count=Count('scan_records'))
    )


def _paginate(request, queryset, serializer_cls):
    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = serializer_cls(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminOrOperator])
def product_list_create(request):
    if request.method == 'GET':
        products = _product_qs().order_by('-created_at')
        return _paginate(request, products, ProductListSerializer)

    # POST -> create (Admin only)
    if not is_admin(request.user):
        return Response({'detail': 'Admin role required.'}, status=status.HTTP_403_FORBIDDEN)
    serializer = ProductCreateSerializer(data=request.data)
    if serializer.is_valid():
        product = serializer.save()
        _generate_qr(product)
        return Response(
            ProductListSerializer(product).data,
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def _generate_qr(product):
    """Generate a signed QR code for a product and save it."""
    verify_url = build_verify_url(product.id)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(verify_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    filename = f"qr_{product.id}.png"
    product.qr_code_image.save(filename, ContentFile(buffer.read()), save=True)
    return buffer


@api_view(['POST'])
@permission_classes([IsAdmin])
def bulk_create_products(request):
    """
    Generate QR-coded units for a catalog product, with auto-incrementing batch numbers.
    Body: {catalog (id), batch_prefix, manufactured_date, quantity (1-500)}
    (product_name/brand may be passed instead of catalog for backward compatibility.)
    """
    catalog_id = request.data.get('catalog')
    catalog = None
    product_name = request.data.get('product_name')
    brand = request.data.get('brand', 'Rahman Trades Bangladesh')

    if catalog_id:
        try:
            catalog = CatalogProduct.objects.get(id=catalog_id)
        except (CatalogProduct.DoesNotExist, ValueError, TypeError):
            return Response(
                {'error': 'Selected catalog product was not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product_name = catalog.name
        brand = catalog.brand

    batch_prefix = request.data.get('batch_prefix', 'BATCH')
    manufactured_date = request.data.get('manufactured_date')
    quantity = request.data.get('quantity', 1)

    if not product_name or not manufactured_date:
        return Response(
            {'error': 'Select a catalog product and a manufactured date.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return Response(
            {'error': 'quantity must be a number.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if quantity < 1 or quantity > 500:
        return Response(
            {'error': 'quantity must be between 1 and 500.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    created_products = []
    with transaction.atomic():
        for i in range(1, quantity + 1):
            batch_number = f"{batch_prefix}-{i:04d}"
            product = Product.objects.create(
                catalog=catalog,
                product_name=product_name,
                brand=brand,
                batch_number=batch_number,
                manufactured_date=manufactured_date,
            )
            _generate_qr(product)
            product._scan_count = 0  # avoid a per-row COUNT when serialising
            created_products.append(product)

    serializer = ProductListSerializer(created_products, many=True)
    return Response({
        'count': len(created_products),
        'products': serializer.data,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAdmin])
def bulk_create_csv(request):
    """
    Bulk create products from CSV upload.
    CSV columns: product_name, brand, batch_number, manufactured_date
    """
    csv_file = request.FILES.get('file')
    if not csv_file:
        return Response(
            {'error': 'No CSV file uploaded. Send as "file" in multipart form.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Guard against oversized uploads exhausting memory (read fully below).
    if csv_file.size > 5 * 1024 * 1024:
        return Response(
            {'error': 'CSV file too large (max 5 MB).'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    import csv
    try:
        decoded = csv_file.read().decode('utf-8').splitlines()
    except UnicodeDecodeError:
        return Response(
            {'error': 'CSV must be UTF-8 encoded.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    reader = csv.DictReader(decoded)

    created_products = []
    errors = []
    for row_num, row in enumerate(reader, start=2):
        product_name = (row.get('product_name') or '').strip()
        brand = (row.get('brand') or 'Rahman Trades Bangladesh').strip()
        batch_number = (row.get('batch_number') or '').strip()
        manufactured_date = (row.get('manufactured_date') or '').strip()

        if not product_name or not batch_number or not manufactured_date:
            errors.append(f"Row {row_num}: missing required fields")
            continue

        try:
            product = Product.objects.create(
                product_name=product_name,
                brand=brand or 'Rahman Trades Bangladesh',
                batch_number=batch_number,
                manufactured_date=manufactured_date,
            )
            _generate_qr(product)
            created_products.append(product)
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    serializer = ProductListSerializer(created_products, many=True)
    return Response({
        'count': len(created_products),
        'errors': errors,
        'products': serializer.data,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAdminOrOperator])
def download_qr_codes(request):
    """Download QR codes as a ZIP file. Query param `ids` = comma-separated UUIDs."""
    ids = request.query_params.get('ids')
    # Only the columns the ZIP actually needs — avoids dragging every field per row.
    base = Product.objects.only('id', 'batch_number', 'qr_code_image')
    if ids:
        id_list = [i.strip() for i in ids.split(',') if i.strip()]
        products = base.filter(id__in=id_list)
    else:
        products = base.all()

    if not products.exists():
        return Response(
            {'error': 'No products found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for product in products.iterator():
            if product.qr_code_image:
                try:
                    img_data = product.qr_code_image.read()
                    safe_name = product.batch_number.replace('/', '-')
                    filename = f"{safe_name}_{str(product.id)[:8]}.png"
                    zf.writestr(filename, img_data)
                except Exception:
                    continue

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="qr_codes.zip"'
    return response


def _activate(product, user):
    """Transition a single product PRINTED -> ACTIVE. Returns (ok, message)."""
    if product.status != Product.STATUS_PRINTED:
        return False, f'already {product.get_status_display().lower()}'
    if not product.is_active:
        return False, 'product is disabled'
    product.status = Product.STATUS_ACTIVE
    product.activated_at = timezone.now()
    product.activated_by = user
    product.save(update_fields=['status', 'activated_at', 'activated_by', 'updated_at'])
    return True, 'activated'


@api_view(['POST'])
@permission_classes([IsAdminOrOperator])
def activate_product(request, product_id):
    """Point-of-sale activation: PRINTED -> ACTIVE (Admin or Operator)."""
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return Response({'detail': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)

    ok, message = _activate(product, request.user)
    if not ok:
        return Response(
            {'status': 'error', 'message': f'Cannot activate: {message}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(ProductListSerializer(product).data)


@api_view(['POST'])
@permission_classes([IsAdminOrOperator])
def bulk_activate_products(request):
    """Activate many products at once. Body: {ids: [uuid, ...]}."""
    ids = request.data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return Response(
            {'error': 'Provide a non-empty "ids" list.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    activated, skipped = [], []
    for product in Product.objects.filter(id__in=ids):
        ok, message = _activate(product, request.user)
        (activated if ok else skipped).append(
            {'id': str(product.id), 'batch_number': product.batch_number, 'result': message}
        )
    return Response({
        'activated_count': len(activated),
        'skipped_count': len(skipped),
        'activated': activated,
        'skipped': skipped,
    })


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAdminOrOperator])
def product_detail(request, product_id):
    try:
        product = _product_qs().get(id=product_id)
    except Product.DoesNotExist:
        return Response(
            {'error': 'Product not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == 'GET':
        serializer = ProductDetailSerializer(product)
        return Response(serializer.data)

    # Writes (PUT/PATCH/DELETE) are Admin only.
    if not is_admin(request.user):
        return Response({'detail': 'Admin role required.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method in ('PUT', 'PATCH'):
        partial = request.method == 'PATCH'
        serializer = ProductCreateSerializer(
            product, data=request.data, partial=partial
        )
        if serializer.is_valid():
            updated_product = serializer.save()
            return Response(ProductListSerializer(updated_product).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Catalog (named products the admin curates)
# ---------------------------------------------------------------------------
def _catalog_qs():
    return CatalogProduct.objects.annotate(_unit_count=Count('units'))


@api_view(['GET', 'POST'])
@permission_classes([IsAdminOrOperator])
def catalog_list_create(request):
    if request.method == 'GET':
        catalog = _catalog_qs().order_by('name')
        return _paginate(request, catalog, CatalogProductSerializer)

    # POST -> create (Admin only)
    if not is_admin(request.user):
        return Response({'detail': 'Admin role required.'}, status=status.HTTP_403_FORBIDDEN)
    serializer = CatalogProductSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAdminOrOperator])
def catalog_detail(request, catalog_id):
    try:
        catalog = _catalog_qs().get(id=catalog_id)
    except CatalogProduct.DoesNotExist:
        return Response({'detail': 'Catalog product not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(CatalogProductSerializer(catalog).data)

    # Writes are Admin only.
    if not is_admin(request.user):
        return Response({'detail': 'Admin role required.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method in ('PUT', 'PATCH'):
        serializer = CatalogProductSerializer(
            catalog, data=request.data, partial=request.method == 'PATCH'
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # DELETE -> units keep working (catalog FK is SET_NULL; names already denormalised).
    catalog.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
