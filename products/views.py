import io
import os
import zipfile
import qrcode
from django.core.files.base import ContentFile
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Product
from .serializers import (
    ProductListSerializer,
    ProductCreateSerializer,
    ProductDetailSerializer,
)


@api_view(['GET', 'POST'])
def product_list_create(request):
    if request.method == 'GET':
        products = Product.objects.all().order_by('-created_at')
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)

    if request.method == 'POST':
        serializer = ProductCreateSerializer(data=request.data)
        if serializer.is_valid():
            product = serializer.save()
            _generate_qr(product)

            return Response(
                ProductListSerializer(product).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://192.168.1.3:5173')


def _generate_qr(product):
    """Generate QR code for a product and save it."""
    verify_url = f"{FRONTEND_URL}/verify/{product.id}"
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
def bulk_create_products(request):
    """
    Bulk create products with auto-incrementing batch numbers.
    Body: {
        product_name: str,
        brand: str (optional),
        batch_prefix: str (e.g. "BATCH-2026"),
        manufactured_date: str (YYYY-MM-DD),
        quantity: int (1-500)
    }
    """
    product_name = request.data.get('product_name')
    brand = request.data.get('brand', 'Rahman Trades Bangladesh')
    batch_prefix = request.data.get('batch_prefix', 'BATCH')
    manufactured_date = request.data.get('manufactured_date')
    quantity = request.data.get('quantity', 1)

    if not product_name or not manufactured_date:
        return Response(
            {'error': 'product_name and manufactured_date are required.'},
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
    for i in range(1, quantity + 1):
        batch_number = f"{batch_prefix}-{i:04d}"
        product = Product.objects.create(
            product_name=product_name,
            brand=brand,
            batch_number=batch_number,
            manufactured_date=manufactured_date,
        )
        _generate_qr(product)
        created_products.append(product)

    serializer = ProductListSerializer(created_products, many=True)
    return Response({
        'count': len(created_products),
        'products': serializer.data,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
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

    import csv
    decoded = csv_file.read().decode('utf-8').splitlines()
    reader = csv.DictReader(decoded)

    created_products = []
    errors = []
    for row_num, row in enumerate(reader, start=2):
        product_name = row.get('product_name', '').strip()
        brand = row.get('brand', 'Rahman Trades Bangladesh').strip()
        batch_number = row.get('batch_number', '').strip()
        manufactured_date = row.get('manufactured_date', '').strip()

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
def download_qr_codes(request):
    """
    Download QR codes as a ZIP file.
    Query params:
        ids: comma-separated product UUIDs (optional, downloads all if omitted)
    """
    ids = request.query_params.get('ids')
    if ids:
        id_list = [i.strip() for i in ids.split(',') if i.strip()]
        products = Product.objects.filter(id__in=id_list)
    else:
        products = Product.objects.all()

    if not products.exists():
        return Response(
            {'error': 'No products found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for product in products:
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


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
def product_detail(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return Response(
            {'error': 'Product not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == 'GET':
        serializer = ProductDetailSerializer(product)
        return Response(serializer.data)

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
