"""Notification dispatch — email (SMTP) + SMS (Twilio).

Every public entry point is wrapped so a provider failure can NEVER break product
verification. Failures are logged and swallowed. Sending is synchronous for now;
move to a task queue (Celery/RQ) when volume warrants it.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger('notifications')


# ---------------------------------------------------------------------------
# Low-level channels
# ---------------------------------------------------------------------------
def _send_email(subject, body, recipients):
    recipients = [r for r in (recipients or []) if r]
    if not recipients:
        return False
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        fail_silently=False,
    )
    logger.info('Email sent to %s: %s', recipients, subject)
    return True


def _send_sms(body, recipients):
    recipients = [r for r in (recipients or []) if r]
    if not recipients:
        return False
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER):
        logger.info('SMS skipped (Twilio not configured): %s', body)
        return False

    from twilio.rest import Client  # imported lazily so the dep is optional

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    for number in recipients:
        client.messages.create(body=body, from_=settings.TWILIO_FROM_NUMBER, to=number)
        logger.info('SMS sent to %s', number)
    return True


# ---------------------------------------------------------------------------
# High-level events (fail-safe)
# ---------------------------------------------------------------------------
def notify_suspicious_scan(product, scan_record, reason='repeat_scan'):
    """Alert the brand that a flagged / not-activated scan occurred."""
    try:
        title = (
            'Counterfeit alert: not-activated product scanned'
            if reason == 'not_activated'
            else 'Counterfeit alert: product re-scanned'
        )
        body = (
            f"{title}\n\n"
            f"Product : {product.product_name} ({product.brand})\n"
            f"Batch   : {product.batch_number}\n"
            f"Product ID: {product.id}\n"
            f"Status  : {product.get_status_display()}\n"
            f"Scanned by: {scan_record.customer_name} <{scan_record.customer_email}>"
            f" / {scan_record.customer_phone or 'no phone'}\n"
            f"IP      : {scan_record.ip_address}\n"
            f"Time    : {scan_record.scanned_at.isoformat()}\n"
        )
        _send_email(title, body, settings.ALERT_RECIPIENT_EMAILS)
        _send_sms(
            f"{title} - {product.product_name} batch {product.batch_number}",
            settings.ALERT_RECIPIENT_PHONES,
        )
    except Exception:  # noqa: BLE001 - notifications must never break verification
        logger.exception('Failed to send suspicious-scan notification')


def notify_customer_genuine(product, scan_record):
    """Optional receipt to the customer confirming a genuine verification."""
    if not settings.NOTIFY_CUSTOMER_ON_GENUINE:
        return
    try:
        subject = f'Authenticity confirmed: {product.product_name}'
        body = (
            f"Thank you for verifying your purchase.\n\n"
            f"Product: {product.product_name} ({product.brand})\n"
            f"Batch  : {product.batch_number}\n"
            f"Verified at: {scan_record.scanned_at.isoformat()}\n\n"
            f"This product is genuine. Keep this email as your verification receipt."
        )
        _send_email(subject, body, [scan_record.customer_email])
    except Exception:  # noqa: BLE001
        logger.exception('Failed to send customer genuine receipt')
