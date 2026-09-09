import os
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import TELEGRAM_BOT_TOKEN, TEMP_DIR, logger
from handlers.start_handler import start_command
from handlers.cancel_handler import cancel_command
from handlers.status_handler import status_command
from handlers.video_handler import handle_video
from handlers.keys_handler import keys_command, keys_callback, handle_key_input
from utils.helpers import force_cleanup_temp_dir, get_free_space_mb

async def error_handler(update: object, context: object) -> None:
    logger.error(f"Xatolik yuz berdi: {context.error}", exc_info=context.error)

def main():
    logger.info("AI Studio bot ishga tushmoqda...")
    
    force_cleanup_temp_dir(TEMP_DIR)
    
    free_space = get_free_space_mb(TEMP_DIR)
    if free_space < 100:
        logger.warning(f"DIQQAT: Tizimda xotira juda kam qolgan! ({free_space} MB)")
    else:
        logger.info(f"Tizim tayyor. Bo'sh xotira: {free_space} MB")
    
    try:
        application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("cancel", cancel_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("keys", keys_command))
        application.add_handler(CallbackQueryHandler(keys_callback, pattern="^keys_"))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_key_input)
        )
        application.add_handler(
            MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video)
        )
        application.add_error_handler(error_handler)

        if os.environ.get("PORT"):
            logger.info("Server muhiti aniqlandi. Webhook rejimi ishga tushirilmoqda...")
            application.run_webhook(
                listen="0.0.0.0",
                port=int(os.environ.get("PORT", 8080)),
                url_path=TELEGRAM_BOT_TOKEN,
                webhook_url=f"{os.environ.get('RENDER_EXTERNAL_URL', '')}/{TELEGRAM_BOT_TOKEN}"
            )
        else:
            logger.info("Telefon/Termux muhiti aniqlandi. Polling rejimi ishga tushirilmoqda...")
            application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.critical(f"Botni ishga tushirishda kritik xato: {e}")

if __name__ == "__main__":
    main()
