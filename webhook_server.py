import os
import logging
from aiohttp import web
from telegram.ext import Application

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

async def health_check(request):
    return web.Response(text="AI Studio Bot is running!")

async def start_webhook(application: Application, token: str):
    if not WEBHOOK_URL:
        logger.warning("RENDER_EXTERNAL_URL topilmadi.")
        return

    app = web.Application()
    app.router.add_get("/", health_check)
    
    webhook_path = f"/{token}"
    app.router.add_post(webhook_path, lambda req: application.process_update(req))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    
    full_webhook_url = f"{WEBHOOK_URL}{webhook_path}"
    await application.bot.set_webhook(url=full_webhook_url)
    
    logger.info(f"Webhook server ishga tushdi. Port: {PORT}")
    await site.start()
