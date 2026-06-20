from django.conf import settings
from django.db import models


class SiteConfig(models.Model):
    """Singleton white-label configuration.

    Lets a deployment be rebranded (name, logo, colours, contact) from the admin
    Settings page or env defaults — no code edits needed to ship for a new client.
    """
    app_name = models.CharField(max_length=80, default='QRShield')
    tagline = models.CharField(max_length=160, default='QR Authentication & Anti-Counterfeit')
    company_name = models.CharField(max_length=120, default='QRShield')
    support_email = models.EmailField(default='support@qrshield.com')
    accent_color = models.CharField(max_length=9, default='#ef4444')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Site configuration'

    def __str__(self):
        return self.app_name

    @classmethod
    def load(cls):
        """Return the singleton row, creating it from env-seeded defaults."""
        from django.conf import settings as dj_settings
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'app_name': getattr(dj_settings, 'BRAND_APP_NAME', 'QRShield'),
                'tagline': getattr(dj_settings, 'BRAND_TAGLINE', 'QR Authentication & Anti-Counterfeit'),
                'company_name': getattr(dj_settings, 'BRAND_COMPANY', 'QRShield'),
                'support_email': getattr(dj_settings, 'BRAND_SUPPORT_EMAIL', 'support@qrshield.com'),
                'accent_color': getattr(dj_settings, 'BRAND_ACCENT', '#ef4444'),
            },
        )
        return obj


class AuditLog(models.Model):
    """An append-only record of significant admin actions."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_entries',
    )
    username = models.CharField(max_length=150, blank=True, default='')  # snapshot
    action = models.CharField(max_length=64)          # e.g. 'product.recall'
    target = models.CharField(max_length=160, blank=True, default='')   # human label
    detail = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['-created_at'])]

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.username} {self.action}'


class FailedLogin(models.Model):
    """One row per failed login attempt — backs the lockout check."""
    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']


class TwoFactor(models.Model):
    """Optional TOTP two-factor secret for a user."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='two_factor',
    )
    secret = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} 2FA={"on" if self.enabled else "off"}'


def log_action(request, action, target='', detail=''):
    """Best-effort audit write — never breaks the request if logging fails."""
    try:
        user = getattr(request, 'user', None)
        AuditLog.objects.create(
            user=user if (user and user.is_authenticated) else None,
            username=(user.username if (user and user.is_authenticated) else ''),
            action=action,
            target=str(target)[:160],
            detail=str(detail)[:255],
        )
    except Exception:
        pass
