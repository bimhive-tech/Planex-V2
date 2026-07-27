"""Thin OpenAI client wrapper. Reads the key from settings (not import time —
settings aren't guaranteed configured yet at module import in every context),
and raises a clear error instead of a confusing SDK failure when it's unset."""
from openai import OpenAI


class AiNotConfigured(Exception):
    """OPENAI_API_KEY isn't set yet — the assistant has nothing to call."""


def get_client() -> OpenAI:
    from django.conf import settings

    if not settings.OPENAI_API_KEY:
        raise AiNotConfigured("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def get_model() -> str:
    from django.conf import settings

    return settings.OPENAI_MODEL
