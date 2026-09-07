import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID, TEMP_DIR
from utils.helpers import get_free_space_mb

logger = logging.getLogger(__name__)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        return

    is_processing = context.user_data.get('is_processing', False)
    process_status = "🔄 Video qayta ishlanmoqda..." if is_processing else "✅ Tizim bo'sh, tayyor."

    free_space = get_free_space_mb(TEMP_DIR)
    
    try:
        temp_files_count = len([name for name in os.listdir(TEMP_DIR) if os.path.isfile(os.path.join(TEMP_DIR, name))])
    except Exception:
        temp_files_count = 0

    warning_msg = ""
    if free_space < 100:
        warning_msg = "\n\n⚠️ <b>DIQQAT:</b> Telefon xotirasi kam qolgan!"

    status_text = (
        "<b>📊 AI Studio Holati</b>\n\n"
        f"<b>Holat:</b> {process_status}\n"
        f"<b>Bo'sh xotira:</b> {free_space} MB\n"
        f"<b>Temp fayllar soni:</b> {temp_files_count} ta\n\n"
        "<i>Buyruqlar:</i>\n"
        "/start - Bot haqida ma'lumot\n"
        "/cancel - Joriy jarayonni bekor qilish\n"
        "/status - Ushbu ma'lumotni ko'rish"
        f"{warning_msg}"
    )

    await update.message.reply_text(status_text, parse_mode="HTML")
