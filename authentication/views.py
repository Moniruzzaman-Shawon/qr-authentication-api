import csv
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Exists, Max, Min, OuterRef, Q, Subquery
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from accounts.permissions import IsAdmin, IsAdminOrOperator
from core.pagination import StandardPagination
from notifications.services import notify_customer_genuine, notify_suspicious_scan
from products.models import Product
from products.qr import verify_signature
from .models import ScanRecord
from .serializers import ScanRecordSerializer, VerifyRequestSerializer


class VerifyThrottle(ScopedRateThrottle):
    scope = 'verify'


class CheckThrottle(ScopedRateThrottle):
    scope = 'check'


def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _mask_email(email):
    """Mask an email for privacy: 'john@email.com' -> 'j***@email.com'."""
    if not email or '@' not in email:
        return 'unknown'
    local, _, domain = email.partition('@')
    first = local[0] if local else '*'
    return f"{first}***@{domain}"


def _record_scan(product, data, request, is_first):
    return ScanRecord.objects.create(
        product=product,
        customer_email=data['email'],
        customer_name=data['name'],
        customer_phone=data.get('phone', ''),
        ip_address=_get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        is_first_scan=is_first,
    )


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([VerifyThrottle])
def verify_product(request, product_id):
    """Customer-facing verification with two-phase activation.

    PRINTED  -> not activated / not authorised for sale (alert)
    ACTIVE   -> GENUINE (records first scan, transitions to VERIFIED)
    VERIFIED/FLAGGED -> SUSPICIOUS (records fraud attempt, transitions to FLAGGED)
    """
    serializer = VerifyRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    data = serializer.validated_data

    # Reject tampered / unsigned QR payloads.
    if not verify_signature(product_id, request.query_params.get('sig')):
        return Response(
            {'status': 'error', 'message': 'Invalid or unsigned QR code.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Lock the product row so concurrent scans are serialised.
    with transaction.atomic():
        try:
            product = Product.objects.select_for_update().get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {'status': 'error', 'message': 'Product not found. This QR code may be invalid.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Recalled / disabled product.
        if not product.is_active:
            scan = _record_scan(product, data, request, is_first=False)
            outcome = ('disabled', scan)
        elif product.status == Product.STATUS_PRINTED:
            # Not yet activated for sale — scanning this is itself a red flag.
            scan = _record_scan(product, data, request, is_first=False)
            outcome = ('not_activated', scan)
        elif product.status == Product.STATUS_ACTIVE:
            # GENUINE: first legitimate scan.
            scan = _record_scan(product, data, request, is_first=True)
            product.status = Product.STATUS_VERIFIED
            product.save(update_fields=['status', 'updated_at'])
            outcome = ('genuine', scan)
        else:
            # Already VERIFIED or FLAGGED -> suspicious.
            scan = _record_scan(product, data, request, is_first=False)
            if product.status != Product.STATUS_FLAGGED:
                product.status = Product.STATUS_FLAGGED
                product.save(update_fields=['status', 'updated_at'])
            outcome = ('suspicious', scan)

    result, scan_record = outcome

    if result == 'genuine':
        notify_customer_genuine(product, scan_record)
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

    if result == 'not_activated':
        notify_suspicious_scan(product, scan_record, reason='not_activated')
        return Response({
            'status': 'not_activated',
            'message': (
                'This product has not been activated for sale. It may be stolen or '
                'counterfeit. Please contact the seller.'
            ),
            'product': {
                'name': product.product_name,
                'brand': product.brand,
                'batch_number': product.batch_number,
            },
        })

    if result == 'disabled':
        notify_suspicious_scan(product, scan_record, reason='not_activated')
        return Response({
            'status': 'suspicious',
            'message': 'This product has been recalled or deactivated. Do not use it.',
            'product': {
                'name': product.product_name,
                'brand': product.brand,
                'batch_number': product.batch_number,
            },
        })

    # suspicious
    first_scan = product.scan_records.filter(is_first_scan=True).first()
    first_scanned_at = first_scan.scanned_at if first_scan else None
    first_email = first_scan.customer_email if first_scan else 'unknown'
    first_date_str = first_scanned_at.strftime('%B %d, %Y') if first_scanned_at else ''
    notify_suspicious_scan(product, scan_record, reason='repeat_scan')

    return Response({
        'status': 'suspicious',
        'message': (
            f'⚠️ WARNING: This code was already verified on {first_date_str}. '
            f'If this was not you, this product may be counterfeit.'
        ),
        'first_scanned_at': first_scanned_at.isoformat() if first_scanned_at else None,
        'first_scanned_by': _mask_email(first_email),
        'scan_count': product.scan_count,
        'product': {
            'name': product.product_name,
            'brand': product.brand,
            'batch_number': product.batch_number,
        },
    })


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([CheckThrottle])
def check_product(request, product_id):
    if not verify_signature(product_id, request.query_params.get('sig')):
        return Response(
            {'status': 'error', 'message': 'Invalid or unsigned QR code.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
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
            'status': product.status,
            'is_activated': product.status != Product.STATUS_PRINTED and product.is_active,
            'scan_count': product.scan_count,
            'is_verified': product.scan_count > 0,
            'is_suspicious': product.is_suspicious,
            'first_scanned_at': first_scan.scanned_at.isoformat() if first_scan else None,
        },
    })


@api_view(['GET'])
@permission_classes([IsAdminOrOperator])
def scan_list(request):
    scans = ScanRecord.objects.select_related('product').all()

    is_first_scan = request.query_params.get('is_first_scan')
    if is_first_scan is not None:
        is_first_scan = is_first_scan.lower() in ('true', '1', 'yes')
        scans = scans.filter(is_first_scan=is_first_scan)

    paginator = StandardPagination()
    page = paginator.paginate_queryset(scans, request)
    serializer = ScanRecordSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAdminOrOperator])
def dashboard_stats(request):
    total_products = Product.objects.count()
    total_scans = ScanRecord.objects.count()
    genuine_scans = ScanRecord.objects.filter(is_first_scan=True).count()
    suspicious_scans = ScanRecord.objects.filter(is_first_scan=False).count()

    today = timezone.now().date()
    scans_today = ScanRecord.objects.filter(scanned_at__date=today).count()

    # Lifecycle breakdown for the dashboard.
    status_counts = {row['status']: row['n'] for row in
                     Product.objects.values('status').annotate(n=Count('id'))}

    recent_suspicious = ScanRecord.objects.filter(
        is_first_scan=False
    ).select_related('product').order_by('-scanned_at')[:10]
    recent_suspicious_data = ScanRecordSerializer(
        recent_suspicious, many=True, context={'request': request}
    ).data

    # Daily genuine/suspicious counts for the last 14 days, aggregated in the DB
    # (so the chart reflects ALL scans, not just the first page of /scans).
    days = int(request.query_params.get('days', 14))
    days = max(1, min(days, 90))
    start = today - timedelta(days=days - 1)
    raw = {
        row['day']: row
        for row in (
            ScanRecord.objects
            .filter(scanned_at__date__gte=start)
            .annotate(day=TruncDate('scanned_at'))
            .values('day')
            .annotate(
                genuine=Count('id', filter=Q(is_first_scan=True)),
                suspicious=Count('id', filter=Q(is_first_scan=False)),
            )
        )
    }
    timeseries = []
    for i in range(days):
        d = start + timedelta(days=i)
        row = raw.get(d)
        timeseries.append({
            'date': d.isoformat(),
            'genuine': row['genuine'] if row else 0,
            'suspicious': row['suspicious'] if row else 0,
        })

    return Response({
        'total_products': total_products,
        'total_scans': total_scans,
        'genuine_scans': genuine_scans,
        'suspicious_scans': suspicious_scans,
        'scans_today': scans_today,
        'status_breakdown': {
            'printed': status_counts.get(Product.STATUS_PRINTED, 0),
            'active': status_counts.get(Product.STATUS_ACTIVE, 0),
            'verified': status_counts.get(Product.STATUS_VERIFIED, 0),
            'flagged': status_counts.get(Product.STATUS_FLAGGED, 0),
        },
        'timeseries': timeseries,
        'recent_suspicious': recent_suspicious_data,
    })


@api_view(['GET'])
@permission_classes([IsAdminOrOperator])
def fraud_alerts(request):
    # A fraud alert is any non-genuine scan: a duplicate scan, OR a scan of a
    # product that was never legitimately activated (PRINTED / recalled). The
    # Exists annotation lets the serializer label each without an extra query.
    genuine_exists = ScanRecord.objects.filter(
        product=OuterRef('product'), is_first_scan=True
    )
    suspicious_scans = (
        ScanRecord.objects
        .filter(is_first_scan=False)
        .select_related('product')
        .annotate(product_has_genuine=Exists(genuine_exists))
        .order_by('-scanned_at')
    )

    paginator = StandardPagination()
    page = paginator.paginate_queryset(suspicious_scans, request)
    serializer = ScanRecordSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAdminOrOperator])
def customer_list(request):
    """List unique customers grouped by email with aggregated scan data."""
    # Latest name/phone per customer via a correlated subquery, so the whole
    # listing is a single query instead of 1 + one lookup per distinct customer.
    latest = ScanRecord.objects.filter(
        customer_email=OuterRef('customer_email')
    ).order_by('-scanned_at')

    customers = (
        ScanRecord.objects
        .values('customer_email')
        .annotate(
            name=Subquery(latest.values('customer_name')[:1]),
            phone=Subquery(latest.values('customer_phone')[:1]),
            total_scans=Count('id'),
            products_verified=Count('product', distinct=True),
            first_scan=Min('scanned_at'),
            last_scan=Max('scanned_at'),
        )
        .order_by('-last_scan')
    )

    result = [
        {
            'email': c['customer_email'],
            'name': c['name'] or '',
            'phone': c['phone'] or '',
            'total_scans': c['total_scans'],
            'products_verified': c['products_verified'],
            'first_scan': c['first_scan'],
            'last_scan': c['last_scan'],
        }
        for c in customers
    ]

    return Response(result)


@api_view(['DELETE'])
@permission_classes([IsAdmin])
def scan_detail(request, scan_id):
    """Remove a single scan record (Admin only) — e.g. dismiss a fraud alert."""
    try:
        scan = ScanRecord.objects.get(id=scan_id)
    except ScanRecord.DoesNotExist:
        return Response({'detail': 'Scan not found.'}, status=status.HTTP_404_NOT_FOUND)
    scan.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'DELETE'])
@permission_classes([IsAdminOrOperator])
def customer_detail(request, email):
    scans = ScanRecord.objects.filter(
        customer_email=email
    ).select_related('product').order_by('-scanned_at')

    if not scans.exists():
        return Response(
            {'error': 'Customer not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # DELETE -> remove all of this customer's scan records (Admin only).
    if request.method == 'DELETE':
        from accounts.roles import is_admin
        if not is_admin(request.user):
            return Response({'detail': 'Admin role required.'}, status=status.HTTP_403_FORBIDDEN)
        deleted, _ = scans.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    latest = scans.first()
    scan_data = ScanRecordSerializer(scans, many=True, context={'request': request}).data

    # One aggregate query instead of four separate COUNT round-trips.
    agg = scans.aggregate(
        total_scans=Count('id'),
        products_verified=Count('product', distinct=True),
        genuine_scans=Count('id', filter=Q(is_first_scan=True)),
        suspicious_scans=Count('id', filter=Q(is_first_scan=False)),
    )

    return Response({
        'email': email,
        'name': latest.customer_name,
        'phone': latest.customer_phone,
        'total_scans': agg['total_scans'],
        'products_verified': agg['products_verified'],
        'genuine_scans': agg['genuine_scans'],
        'suspicious_scans': agg['suspicious_scans'],
        'scans': scan_data,
    })


# ---------------------------------------------------------------------------
# CSV exports
# ---------------------------------------------------------------------------
def _csv_response(filename, header, rows):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


@api_view(['GET'])
@permission_classes([IsAdmin])
def scan_export(request):
    """Download the full scan history as CSV (Admin only — contains customer PII)."""
    scans = ScanRecord.objects.select_related('product').order_by('-scanned_at')
    rows = (
        [
            s.scanned_at.isoformat(),
            s.product.product_name if s.product else '',
            s.product.batch_number if s.product else '',
            'Genuine' if s.is_first_scan else 'Suspicious',
            s.customer_name,
            s.customer_email,
            s.customer_phone or '',
            s.ip_address or '',
        ]
        for s in scans.iterator()
    )
    return _csv_response(
        'scans.csv',
        ['Scanned At', 'Product', 'Batch', 'Result', 'Customer', 'Email', 'Phone', 'IP'],
        rows,
    )


@api_view(['GET'])
@permission_classes([IsAdmin])
def customer_export(request):
    """Download the aggregated customer list as CSV (Admin only — contains PII)."""
    latest = ScanRecord.objects.filter(
        customer_email=OuterRef('customer_email')
    ).order_by('-scanned_at')
    customers = (
        ScanRecord.objects
        .values('customer_email')
        .annotate(
            name=Subquery(latest.values('customer_name')[:1]),
            phone=Subquery(latest.values('customer_phone')[:1]),
            total_scans=Count('id'),
            products_verified=Count('product', distinct=True),
            first_scan=Min('scanned_at'),
            last_scan=Max('scanned_at'),
        )
        .order_by('-last_scan')
    )
    rows = (
        [
            c['name'] or '',
            c['customer_email'],
            c['phone'] or '',
            c['total_scans'],
            c['products_verified'],
            c['first_scan'].isoformat() if c['first_scan'] else '',
            c['last_scan'].isoformat() if c['last_scan'] else '',
        ]
        for c in customers
    )
    return _csv_response(
        'customers.csv',
        ['Name', 'Email', 'Phone', 'Total Scans', 'Products Verified', 'First Scan', 'Last Scan'],
        rows,
    )
