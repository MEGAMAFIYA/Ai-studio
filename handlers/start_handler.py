import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Foydalanuvchi"

    if user_id != ADMIN_ID:
        logger.warning(f"Ruxsatsiz kirish urinishi. User ID: {user_id}")
        await update.message.reply_text("⛔ Sizda bu botdan foydalanish huquqi yo'q.")
        return

    logger.info(f"Admin ({user_id}) botni ishga tushirdi.")
    
    welcome_text = (
        f"🎬 Salom, {first_name}!\n\n"
        f"Xush kelibsiz <b>AI Studio</b> botiga.\n"
        f"Menga kino (video) yuklang, men uni o'zbek tiliga tarjima qilib .srt subtitr qilib beraman.\n\n"
        f"Buyruqlar:\n"
        f"/cancel - Jarayonni bekor qilish\n"
        f"/status - Tizim holatini ko'rish\n"
        f"/keys - AI tarjima kalitlarini boshqarish"
    )
    
    await update.message.reply_text(welcome_text, parse_mode="HTML")
