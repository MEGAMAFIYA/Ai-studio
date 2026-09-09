import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_env_variable(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        logger.error(f"Kritik xato: {var_name} .env faylida topilmadi!")
        raise ValueError(f"{var_name} sozlanmagan.")
    return value

TELEGRAM_BOT_TOKEN = get_env_variable("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = get_env_variable("GROQ_API_KEY")

# Uzbekcha dublyaj uchun rasmiy Azure Speech xizmati (edge-tts o'rniga —
# edge-tts norasmiy usul bo'lgani uchun Microsoft tomonidan doimiy
# bloklanib turadi). Bepul olish: portal.azure.com'da "Speech" resursi
# yarating (F0 — bepul tarif, oyiga 500,000 belgigacha).
AZURE_SPEECH_KEY = get_env_variable("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = get_env_variable("AZURE_SPEECH_REGION")

try:
    ADMIN_ID = int(get_env_variable("ADMIN_ID"))
except ValueError:
    logger.error("ADMIN_ID raqam bo'lishi kerak!")
    raise ValueError("ADMIN_ID noto'g'ri formatda.")

TEMP_DIR = "temp"

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)
