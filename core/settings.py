import os
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
env = environ.Env(
    DEBUG=(bool, False),
)
# Read a .env file if present (local dev). In production, real env vars win.
environ.Env.read_env(BASE_DIR / '.env')

DEBUG = env.bool('DEBUG', default=False)

# SECRET_KEY is required in production. A dev fallback is used only when DEBUG.
SECRET_KEY = env.str(
    'SECRET_KEY',
    default='django-insecure-qr-auth-dev-key-change-in-production' if DEBUG else '',
)
if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY environment variable must be set when DEBUG=False.')

# Key used to sign QR payloads. Defaults to SECRET_KEY but can be rotated separately.
QR_SIGNING_KEY = env.str('QR_SIGNING_KEY', default=SECRET_KEY)

ALLOWED_HOSTS = env.list(
    'ALLOWED_HOSTS',
    default=['localhost', '127.0.0.1'] if DEBUG else [],
)

# URL of the customer-facing frontend; embedded in generated QR codes.
FRONTEND_URL = env.str('FRONTEND_URL', default='http://localhost:5173')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    # Local
    'accounts',
    'products',
    'authentication',
    'notifications',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
if env.str('DATABASE_URL', default='') or env.str('DB_NAME', default=''):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env.str('DB_NAME', default='qr_auth'),
            'USER': env.str('DB_USER', default='postgres'),
            'PASSWORD': env.str('DB_PASSWORD', default=''),
            'HOST': env.str('DB_HOST', default='localhost'),
            'PORT': env.str('DB_PORT', default='5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list(
    'CORS_ALLOWED_ORIGINS',
    default=['http://localhost:5173', 'http://127.0.0.1:5173'] if DEBUG else [],
)

# ---------------------------------------------------------------------------
# REST Framework + JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': (
        [
            'rest_framework.renderers.JSONRenderer',
            'rest_framework.renderers.BrowsableAPIRenderer',
        ]
        if DEBUG
        else ['rest_framework.renderers.JSONRenderer']
    ),
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'verify': env.str('THROTTLE_VERIFY', default='20/min'),
        'check': env.str('THROTTLE_CHECK', default='60/min'),
        'login': env.str('THROTTLE_LOGIN', default='10/min'),
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=env.int('JWT_ACCESS_MINUTES', default=30)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=env.int('JWT_REFRESH_DAYS', default=7)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'QRShield API',
    'DESCRIPTION': 'QRShield — QR authentication & anti-counterfeit. Product '
                   'verification via one-time-use QR codes with two-phase activation.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# ---------------------------------------------------------------------------
# Email / SMS notifications
# ---------------------------------------------------------------------------
if DEBUG:
    EMAIL_BACKEND = env.str(
        'EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend'
    )
else:
    EMAIL_BACKEND = env.str(
        'EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend'
    )
EMAIL_HOST = env.str('EMAIL_HOST', default='')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env.str('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env.str('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env.str('DEFAULT_FROM_EMAIL', default='alerts@qrshield.com')

# Where fraud / not-activated alerts are sent (comma-separated).
ALERT_RECIPIENT_EMAILS = env.list('ALERT_RECIPIENT_EMAILS', default=[])
ALERT_RECIPIENT_PHONES = env.list('ALERT_RECIPIENT_PHONES', default=[])
NOTIFY_CUSTOMER_ON_GENUINE = env.bool('NOTIFY_CUSTOMER_ON_GENUINE', default=False)

# Twilio (SMS). Leave blank to disable SMS.
TWILIO_ACCOUNT_SID = env.str('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = env.str('TWILIO_AUTH_TOKEN', default='')
TWILIO_FROM_NUMBER = env.str('TWILIO_FROM_NUMBER', default='')

# White-label branding — seeds the editable SiteConfig singleton on first run.
BRAND_APP_NAME = env.str('BRAND_APP_NAME', default='QRShield')
BRAND_TAGLINE = env.str('BRAND_TAGLINE', default='QR Authentication & Anti-Counterfeit')
BRAND_COMPANY = env.str('BRAND_COMPANY', default='QRShield')
BRAND_SUPPORT_EMAIL = env.str('BRAND_SUPPORT_EMAIL', default='support@qrshield.com')
BRAND_ACCENT = env.str('BRAND_ACCENT', default='#ef4444')

# Login security: lock an account after this many failed attempts, for this long.
LOGIN_MAX_ATTEMPTS = env.int('LOGIN_MAX_ATTEMPTS', default=5)
LOGIN_LOCKOUT_MINUTES = env.int('LOGIN_LOCKOUT_MINUTES', default=15)

# Initial admin (seeded by `manage.py seed_admin`).
INITIAL_ADMIN_USERNAME = env.str('INITIAL_ADMIN_USERNAME', default='admin')
INITIAL_ADMIN_EMAIL = env.str('INITIAL_ADMIN_EMAIL', default='admin@qrshield.com')
INITIAL_ADMIN_PASSWORD = env.str('INITIAL_ADMIN_PASSWORD', default='')

# ---------------------------------------------------------------------------
# Security headers (production only)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {name} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'root': {'handlers': ['console'], 'level': env.str('LOG_LEVEL', default='INFO')},
    'loggers': {
        'notifications': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'authentication': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
