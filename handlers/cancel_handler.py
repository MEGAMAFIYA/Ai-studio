import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from config import ADMIN_ID

logger = logging.getLogger(__name__)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        return

    logger.info(f"Admin ({user_id}) jarayonni bekor qildi.")
    context.user_data.clear()
    
    await update.message.reply_text("❌ Joriy jarayon bekor qilindi.")
    return ConversationHandler.END
