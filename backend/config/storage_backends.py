"""Private R2 storage backend for user media and report assets."""
from django.conf import settings
from storages.backends.s3 import S3Storage


class PrivateR2Storage(S3Storage):
    """Cloudflare R2 via S3 API; keeps objects private and serves signed URLs."""

    access_key = settings.R2_ACCESS_KEY_ID
    secret_key = settings.R2_SECRET_ACCESS_KEY
    bucket_name = settings.R2_BUCKET
    endpoint_url = settings.R2_ENDPOINT_URL
    region_name = "auto"
    signature_version = "s3v4"
    addressing_style = "path"
    querystring_auth = True
    querystring_expire = settings.R2_PRESIGNED_URL_EXPIRY
    default_acl = "private"
    file_overwrite = False
    custom_domain = None
