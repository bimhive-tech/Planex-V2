"""Production settings (Railway). DEBUG off, strict hosts, secure cookies."""
from .base import *  # noqa: F401,F403

DEBUG = False

# Behind Railway's proxy; trust the forwarded protocol so secure cookies work.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
