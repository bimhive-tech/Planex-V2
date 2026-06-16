"""Shared Django settings. All secrets and tunables come from environment variables."""
from datetime import timedelta
from pathlib import Path

import dj_database_url
import environ

# backend/  (this file is config/settings/base.py -> up 3 levels)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Load a local .env if present (dev convenience; prod uses Railway-injected vars).
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

# --- Core security ---------------------------------------------------------
# NOTE: set a real DJANGO_SECRET_KEY in prod (Railway). The default below is only
# for local dev; it's long enough to avoid JWT key-length warnings but is NOT secret.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me-0123456789abcdef")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# --- Applications ----------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.projects",
    "apps.reports",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database --------------------------------------------------------------
# Railway injects DATABASE_URL; parse it. CONN_MAX_AGE keeps connections warm.
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL"),
        conn_max_age=env.int("DB_CONN_MAX_AGE", default=600),
        ssl_require=env.bool("DB_SSL_REQUIRE", default=False),
    )
}

# --- Auth ------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- DRF -------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.accounts.authentication.CookieJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.accounts.pagination.StandardPagination",
    "PAGE_SIZE": env.int("DEFAULT_PAGE_SIZE", default=25),
    "EXCEPTION_HANDLER": "apps.accounts.exceptions.api_exception_handler",
}

# --- JWT (httpOnly cookie auth) -------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# Cookie names + flags consumed by accounts.authentication and the auth views.
AUTH_COOKIE_ACCESS = "planex_access"
AUTH_COOKIE_REFRESH = "planex_refresh"
AUTH_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=not DEBUG)
AUTH_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE", default="Lax")
AUTH_COOKIE_DOMAIN = env("AUTH_COOKIE_DOMAIN", default=None)

# --- CORS ------------------------------------------------------------------
# In prod the frontend is same-origin (Next proxies /api), so CORS is mostly a
# dev/safety net. Credentials must be allowed for cookie auth.
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"])

# --- i18n / tz -------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files (Django admin / DRF browsable API only) ------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Logging (Railway captures stdout/stderr) ------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
}
