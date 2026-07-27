"""Selectable OpenAI models for the chat's per-conversation model picker.
Prices are per 1M tokens, verified against platform.openai.com/docs/pricing
as of the GPT-5.6 family's July 2026 GA release — check there before trusting
these numbers long after this was written, pricing pages change."""

AVAILABLE_MODELS = [
    {"id": "gpt-5.6-luna", "label": "Luna — fastest & cheapest", "input_price": 1.00, "output_price": 6.00},
    {"id": "gpt-5.6-terra", "label": "Terra — balanced (recommended)", "input_price": 2.50, "output_price": 15.00},
    {"id": "gpt-5.6-sol", "label": "Sol — flagship, most expensive", "input_price": 5.00, "output_price": 30.00},
]
AVAILABLE_MODEL_IDS = {m["id"] for m in AVAILABLE_MODELS}
DEFAULT_MODEL = "gpt-5.6-terra"
