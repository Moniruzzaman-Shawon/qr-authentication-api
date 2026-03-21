from django.db.models import Count, Max, Min
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from products.models import Product
from .models import ScanRecord
from .serializers import ScanRecordSerializer, VerifyRequestSerializer


def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _mask_email(email):
    """Mask email for privacy: j***@email.com"""
    local, domain = email.split('@')
    if len(local) <= 1:
        masked_local = local[0] + '***'
    else:
        masked_local = local[0] + '***'
    return f"{masked_local}@{domain}"


@api_view(['POST'])
def verify_product(request, product_id):
    # Validate request body
    serializer = VerifyRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Look up product
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return Response(
            {'status': 'error', 'message': 'Product not found. This QR code may be invalid.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    data = serializer.validated_data
    ip_address = _get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    current_scan_count = product.scan_count

    if current_scan_count == 0:
        # GENUINE - first scan
        scan_record = ScanRecord.objects.create(
            product=product,
            customer_email=data['email'],
            customer_name=data['name'],
            customer_phone=data.get('phone', ''),
            ip_address=ip_address,
            user_agent=user_agent,
            is_first_scan=True,
        )
        return Response({
            'status': 'genuine',
            'message': 'This is an authentic product. Thank you for verifying!',
            'product': {
                'name': product.product_name,
                'brand': product.brand,
                'batch_number': product.batch_number,
                'manufactured_date': str(product.manufactured_date),
            },
            'verified_at': scan_record.scanned_at.isoformat(),
        })
    else:
        # SUSPICIOUS - already scanned before
        first_scan = product.scan_records.filter(is_first_scan=True).first()
        first_scanned_at = first_scan.scanned_at if first_scan else None
        first_scanned_email = first_scan.customer_email if first_scan else 'unknown'

        # Still create a record to track the fraud attempt
        ScanRecord.objects.create(
            product=product,
            customer_email=data['email'],
            customer_name=data['name'],
            customer_phone=data.get('phone', ''),
            ip_address=ip_address,
            user_agent=user_agent,
            is_first_scan=False,
        )

        first_date_str = ''
        if first_scanned_at:
            first_date_str = first_scanned_at.strftime('%B %d, %Y')

        return Response({
            'status': 'suspicious',
            'message': (
                f'\u26a0\ufe0f WARNING: This code was already verified on {first_date_str}. '
                f'If this was not you, this product may be counterfeit.'
            ),
            'first_scanned_at': first_scanned_at.isoformat() if first_scanned_at else None,
            'first_scanned_by': _mask_email(first_scanned_email),
            'scan_count': current_scan_count + 1,  # include the one we just created
            'product': {
                'name': product.product_name,
                'brand': product.brand,
                'batch_number': product.batch_number,
            },
        })


@api_view(['GET'])
def check_product(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return Response(
            {'status': 'error', 'message': 'Product not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    first_scan = product.scan_records.filter(is_first_scan=True).first()

    return Response({
        'product': {
            'id': str(product.id),
            'name': product.product_name,
            'brand': product.brand,
            'batch_number': product.batch_number,
            'manufactured_date': str(product.manufactured_date),
            'is_active': product.is_active,
        },
        'scan_status': {
            'scan_count': product.scan_count,
            'is_verified': product.scan_count > 0,
            'is_suspicious': product.is_suspicious,
            'first_scanned_at': first_scan.scanned_at.isoformat() if first_scan else None,
        },
    })


@api_view(['GET'])
def scan_list(request):
    scans = ScanRecord.objects.select_related('product').all()

    # Filter by is_first_scan if query param provided
    is_first_scan = request.query_params.get('is_first_scan')
    if is_first_scan is not None:
        is_first_scan = is_first_scan.lower() in ('true', '1', 'yes')
        scans = scans.filter(is_first_scan=is_first_scan)

    serializer = ScanRecordSerializer(scans, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def dashboard_stats(request):
    total_products = Product.objects.count()
    total_scans = ScanRecord.objects.count()
    genuine_scans = ScanRecord.objects.filter(is_first_scan=True).count()
    suspicious_scans = ScanRecord.objects.filter(is_first_scan=False).count()

    today = timezone.now().date()
    scans_today = ScanRecord.objects.filter(scanned_at__date=today).count()

    recent_suspicious = ScanRecord.objects.filter(
        is_first_scan=False
    ).select_related('product').order_by('-scanned_at')[:10]

    recent_suspicious_data = ScanRecordSerializer(recent_suspicious, many=True).data

    return Response({
        'total_products': total_products,
        'total_scans': total_scans,
        'genuine_scans': genuine_scans,
        'suspicious_scans': suspicious_scans,
        'scans_today': scans_today,
        'recent_suspicious': recent_suspicious_data,
    })


@api_view(['GET'])
def fraud_alerts(request):
    suspicious_scans = ScanRecord.objects.filter(
        is_first_scan=False
    ).select_related('product').order_by('-scanned_at')

    serializer = ScanRecordSerializer(suspicious_scans, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def customer_list(request):
    """
    List all unique customers grouped by email.
    Returns: name, email, phone, total_scans, products_verified, first_scan, last_scan
    """
    customers = (
        ScanRecord.objects
        .values('customer_email')
        .annotate(
            total_scans=Count('id'),
            products_verified=Count('product', distinct=True),
            first_scan=Min('scanned_at'),
            last_scan=Max('scanned_at'),
        )
        .order_by('-last_scan')
    )

    # Enrich with name and phone from their latest scan
    result = []
    for c in customers:
        latest = ScanRecord.objects.filter(
            customer_email=c['customer_email']
        ).order_by('-scanned_at').first()

        result.append({
            'email': c['customer_email'],
            'name': latest.customer_name if latest else '',
            'phone': latest.customer_phone if latest else '',
            'total_scans': c['total_scans'],
            'products_verified': c['products_verified'],
            'first_scan': c['first_scan'],
            'last_scan': c['last_scan'],
        })

    return Response(result)


@api_view(['GET'])
def customer_detail(request, email):
    """
    Get all scan records for a specific customer email.
    """
    scans = ScanRecord.objects.filter(
        customer_email=email
    ).select_related('product').order_by('-scanned_at')

    if not scans.exists():
        return Response(
            {'error': 'Customer not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    latest = scans.first()
    scan_data = ScanRecordSerializer(scans, many=True).data

    return Response({
        'email': email,
        'name': latest.customer_name,
        'phone': latest.customer_phone,
        'total_scans': scans.count(),
        'products_verified': scans.values('product').distinct().count(),
        'genuine_scans': scans.filter(is_first_scan=True).count(),
        'suspicious_scans': scans.filter(is_first_scan=False).count(),
        'scans': scan_data,
    })
