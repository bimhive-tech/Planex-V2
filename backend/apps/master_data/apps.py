"""App config for the master_data app."""
from django.apps import AppConfig


class MasterDataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.master_data"
    label = "master_data"
