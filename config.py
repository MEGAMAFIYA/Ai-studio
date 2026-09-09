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
# IXTIYORIY: sozlanmasa, bot baribir ishga tushadi — faqat dublyaj (TTS)
# bosqichi ishlamaydi, subtitr/tarjima kabi boshqa funksiyalar ishlayveradi.
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "")

if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
    logger.warning(
        "AZURE_SPEECH_KEY/AZURE_SPEECH_REGION sozlanmagan — "
        "o'zbekcha dublyaj (TTS) bosqichi ishlamaydi."
    )

# Speaker diarization (pyannote.audio) uchun. HuggingFace'da
# "pyannote/speaker-diarization-3.1" VA "pyannote/segmentation-3.0"
# litsenziyasini qabul qilib, shu yerdan token oling:
# https://huggingface.co/settings/tokens
# IXTIYORIY: sozlanmasa, bot baribir ishga tushadi — faqat barcha
# xarakterlar bitta ovozda gapiradi (diarizatsiya o'tkazib yuboriladi).
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "")

if not HUGGINGFACE_TOKEN:
    logger.warning(
        "HUGGINGFACE_TOKEN sozlanmagan — diarizatsiya o'tkazib yuboriladi "
        "(barcha xarakterlar bitta ovozda gapiradi)."
    )

try:
    ADMIN_ID = int(get_env_variable("ADMIN_ID"))
except ValueError:
    logger.error("ADMIN_ID raqam bo'lishi kerak!")
    raise ValueError("ADMIN_ID noto'g'ri formatda.")

TEMP_DIR = "temp"

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)
