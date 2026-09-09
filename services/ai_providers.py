import logging

from openai import AsyncOpenAI

from config import GROQ_API_KEY
from services import key_store

logger = logging.getLogger(__name__)

# Barchasi OpenAI-mos ("OpenAI-compatible") chat completions formatida
# ishlaydi — faqat base_url, model va kalit farq qiladi. Shu sabab
# hammasini bitta umumiy funksiya orqali chaqirish mumkin.
#
# Tartib = urinish tartibi (fallback ketma-ketligi). Groq birinchi, chunki
# u allaqachon config.py orqali (har doim mavjud) sozlangan.
PROVIDERS = {
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "openai/gpt-oss-120b",
        "signup_url": "https://console.groq.com/keys",
    },
    "gemini": {
        "label": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.5-flash",
        "signup_url": "https://aistudio.google.com/apikey",
    },
    "cerebras": {
        "label": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "default_model": "llama-3.3-70b",
        "signup_url": "https://cloud.cerebras.ai",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "signup_url": "https://openrouter.ai/keys",
    },
    "sambanova": {
        "label": "SambaNova",
        "base_url": "https://api.sambanova.ai/v1",
        "default_model": "Meta-Llama-3.3-70B-Instruct",
        "signup_url": "https://cloud.sambanova.ai/apis",
    },
    "mistral": {
        "label": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest",
        "signup_url": "https://console.mistral.ai/api-keys",
    },
    "nvidia": {
        "label": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "default_model": "meta/llama-3.3-70b-instruct",
        "signup_url": "https://build.nvidia.com",
    },
    "vercel": {
        "label": "Vercel AI Gateway",
        "base_url": "https://ai-gateway.vercel.sh/v1",
        "default_model": "openai/gpt-4o-mini",
        "signup_url": "https://vercel.com/docs/ai-gateway",
        "note": "Bu bepul emas — Vercel balansingizdan yechiladi.",
    },
}

# Fallback tartibi: avval bepul va saxiy limitli provayderlar, oxirida
# pullik bo'lishi mumkin bo'lgan Vercel.
PRIORITY_ORDER = [
    "groq", "gemini", "cerebras", "openrouter",
    "sambanova", "mistral", "nvidia", "vercel",
]


def _get_available_keys(provider_id: str) -> list:
    """Shu provayder uchun urinib ko'rish mumkin bo'lgan kalitlar ro'yxati."""
    keys = list(key_store.get_keys(provider_id))
    if provider_id == "groq" and GROQ_API_KEY and GROQ_API_KEY not in keys:
        # .env'dagi asosiy Groq kaliti har doim ro'yxatda birinchi bo'lsin.
        keys.insert(0, GROQ_API_KEY)
    return keys


def iter_available_providers():
    """(provider_id, api_key) juftliklarini urinish tartibida qaytaradi."""
    for provider_id in PRIORITY_ORDER:
        for api_key in _get_available_keys(provider_id):
            yield provider_id, api_key


async def call_chat_completion(provider_id: str, api_key: str, messages: list,
                                temperature: float = 0.3, max_tokens: int = 2048) -> str:
    """Berilgan provayder+kalit bilan chat completion so'rovini yuboradi."""
    cfg = PROVIDERS[provider_id]
    client = AsyncOpenAI(api_key=api_key, base_url=cfg["base_url"])

    completion = await client.chat.completions.create(
        model=cfg["default_model"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return completion.choices[0].message.content.strip()
