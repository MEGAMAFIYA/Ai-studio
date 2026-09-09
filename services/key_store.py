import os
import json
import logging

logger = logging.getLogger(__name__)

KEYS_FILE = os.path.join("data", "ai_keys.json")

# DIQQAT: Render'ning bepul/oddiy tarifida disk doimiy emas — bu yerga
# botdan qo'shilgan kalitlar har qayta deploy qilinganda o'chib ketadi
# (agar "Persistent Disk" pullik xizmati ulanmagan bo'lsa).

os.makedirs(os.path.dirname(KEYS_FILE), exist_ok=True)


def _load() -> dict:
    if not os.path.exists(KEYS_FILE):
        return {}
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Kalitlar faylini o'qishda xato: {e}")
        return {}


def _save(data: dict) -> None:
    try:
        with open(KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Kalitlar faylini yozishda xato: {e}")


def get_keys(provider_id: str) -> list:
    """Berilgan provayder uchun saqlangan kalitlar ro'yxatini qaytaradi."""
    return _load().get(provider_id, [])


def get_all_keys() -> dict:
    return _load()


def add_key(provider_id: str, api_key: str) -> None:
    data = _load()
    data.setdefault(provider_id, [])
    if api_key not in data[provider_id]:
        data[provider_id].append(api_key)
    _save(data)


def remove_key(provider_id: str, index: int) -> bool:
    data = _load()
    keys = data.get(provider_id, [])
    if 0 <= index < len(keys):
        keys.pop(index)
        data[provider_id] = keys
        _save(data)
        return True
    return False


def mask_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "•" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"
