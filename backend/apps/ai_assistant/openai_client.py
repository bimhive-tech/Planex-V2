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
    # A bounded timeout matters more here than usual: a very large tool
    # result (e.g. a whole imported schedule tree) replayed in a big
    # conversation can make a call slow enough to otherwise hang the request
    # indefinitely instead of failing with a clear, catchable error.
    return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=90.0, max_retries=1)


def get_model() -> str:
    from django.conf import settings

    return settings.OPENAI_MODEL
