import os
from datetime import timedelta
from pathlib import Path
from re import S
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY SETTINGS
# ================
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = True
ALLOWED_HOSTS = []

# Application definition
# ====================
DJANGO_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_celery_beat',
    'django_celery_results',
    'django_filters',
    'channels',
]

LOCAL_APPS = [
    'apps.users',
    'apps.projects',
    'apps.tasks',
    'apps.notifications',
    'apps.subscriptions',
    'apps.admins',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Middleware Configuration
# ======================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.users.middleware.LastSeenMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# URL Configuration
# ===============
ROOT_URLCONF = 'project_planner.urls'

# Template Configuration
# ====================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
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

WSGI_APPLICATION = 'project_planner.wsgi.application'
ASGI_APPLICATION = 'project_planner.asgi.application'

# Database Configuration
# ====================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Authentication Configuration
# =========================
AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        },
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# ==================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True

# Static Files Configuration
# ========================
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Media Files Configuration
# =======================
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default Primary Key Field
# =======================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



# Cache Configuration
# =================
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://127.0.0.1:6379/0",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {"max_connections": 100}
        },
        'KEY_PREFIX': 'project_planner',
    }
}

# Channel Layers Configuration
# ========================
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [('127.0.0.1', 6379)],
        },
    },
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# REST Framework Configuration
# =========================
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated', 
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend'
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '1000/day',
        'anon': '100/hour',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'PAGE_SIZE_QUERY_PARAM': 'page_size',
    'MAX_PAGE_SIZE': 100,
}

# JWT Configuration
# ===============
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
}

# API Documentation Configuration
# ============================
SPECTACULAR_SETTINGS = {
    'TITLE': 'Project Planner API',
    'DESCRIPTION': 'API documentation for Project Planner.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'DISABLE_WARNINGS': True,
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
        'displayOperationId': True,
    },
    'TAGS': [
        {'name': 'Users', 'description': 'User management endpoints'},
        {'name': 'Admin', 'description': 'Administrative endpoints'},
        {'name': 'Projects', 'description': 'Project management endpoints'},
        {'name': 'Tasks', 'description': 'Task management endpoints'},
        {'name': 'Subscriptions', 'description': 'Subscription management endpoints'},
        {'name': 'Notifications', 'description': 'Notification management endpoints'},
    ],
}

# Email Configuration
# =================
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND')
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS') == 'True'
EMAIL_PORT = int(os.getenv('EMAIL_PORT'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('EMAIL_HOST_USER')

# Celery Configuration
# ==================
# if not using redis password then url = 'redis://localhost:6379/0'
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Dhaka'
CELERY_TASK_RESULT_EXPIRES = 3600

# Stripe Configuration
# ====================

STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
# to use stripe webhook run this command in terminal : stripe listen --forward-to localhost:4242/webhook
# tigger events to test webhook : stripe trigger payment_intent.succeeded
FRONTEND_URL = 'http://localhost:8000'


# For development purposes, allow all origins
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# System health check settings
LOG_FILE_MAX_SIZE_MB = 50
NETWORK_LATENCY_THRESHOLD_MS = 500
QUEUE_TASK_THRESHOLD = 100

# Logging configuration
from project_planner.logging import get_logger
project_logger = get_logger('project_planner')