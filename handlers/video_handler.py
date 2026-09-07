import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID, TEMP_DIR
from utils.helpers import (
    cleanup_files, 
    create_srt_file, 
    get_free_space_mb, 
    safe_edit_message,
    sanitize_filename
)
from services.media_service import extract_audio
from services.ai_service import transcribe_audio, translate_text_to_uzbek

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024
MIN_FREE_SPACE_MB = 150

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Ruxsat yo'q.")
        return

    if context.user_data.get('is_processing'):
        await update.message.reply_text("⚠️ Iltimos kuting, oldingi video hali qayta ishlanmoqda.\n/cancel ni bosing.")
        return

    video = update.message.video or update.message.document
    if not video:
        return

    mime_type = video.mime_type if hasattr(video, 'mime_type') else ""
    if mime_type and not mime_type.startswith("video/"):
        await update.message.reply_text(f"⚠️ Noto'g'ri format! Faqat video qabul qilinadi.")
        return

    file_size = video.file_size if hasattr(video, 'file_size') else 0
    if file_size and file_size > MAX_FILE_SIZE:
        await update.message.reply_text(f"⚠️ Fayl juda katta! Maksimal hajm: 50MB.")
        return

    free_space = get_free_space_mb(TEMP_DIR)
    if free_space < MIN_FREE_SPACE_MB:
        await update.message.reply_text(f"⛔ Telefonda joy yetarli emas! ({free_space} MB)")
        return

    context.user_data['is_processing'] = True
    status_msg = await update.message.reply_text("⏳ Jarayon boshlandi...\n1/5. Video yuklanmoqda...")

    video_path = ""
    audio_path = ""
    srt_path = ""

    try:
        original_name = getattr(video, 'file_name', None) or getattr(video, 'file_unique_id', 'unknown')
        safe_base_name = sanitize_filename(os.path.splitext(original_name)[0])

        file = await context.bot.get_file(video.file_id)
        video_path = os.path.join(TEMP_DIR, f"{safe_base_name}.mp4")
        await file.download_to_drive(video_path)
        
        if not context.user_data.get('is_processing'):
            raise asyncio.CancelledError("Bekor qilindi.")

        await safe_edit_message(status_msg, "🎬 2/5. Videodan audio ajratilmoqda...")

        audio_path = os.path.join(TEMP_DIR, f"{safe_base_name}.ogg")
        await extract_audio(video_path, audio_path)
        await cleanup_files(video_path)
        video_path = ""

        if not context.user_data.get('is_processing'):
            raise asyncio.CancelledError("Bekor qilindi.")

        await safe_edit_message(status_msg, "🎙️ 3/5. Nutq matnga aylantirilmoqda...")

        segments = await transcribe_audio(audio_path)
        await cleanup_files(audio_path)
        audio_path = ""

        if not context.user_data.get('is_processing'):
            raise asyncio.CancelledError("Bekor qilindi.")

        if not segments:
            await safe_edit_message(status_msg, "⚠️ Videoda nutq aniqlanmadi.")
            return

        await safe_edit_message(status_msg, f"✅ Matn tayyor ({len(segments)} ta).\n🌐 4/5. Tarjima qilinmoqda...")

        translated_segments = await translate_text_to_uzbek(segments)

        if not context.user_data.get('is_processing'):
            raise asyncio.CancelledError("Bekor qilindi.")

        await safe_edit_message(status_msg, "📝 5/5. Subtitr (.srt) yaratilmoqda...")

        srt_name = f"{safe_base_name}_uz.srt"
        srt_path = os.path.join(TEMP_DIR, srt_name)
        
        success = await create_srt_file(translated_segments, srt_path)
        
        if not success:
            raise Exception("SRT yaratishda xatolik.")

        with open(srt_path, 'rb') as srt_file:
            await update.message.reply_document(
                document=srt_file,
                filename=srt_name,
                caption="✅ Tayyor! Kinoning o'zbekcha subtitri."
            )

        try:
            await status_msg.delete()
        except Exception:
            pass
            
        logger.info(f"Jarayon tugadi: {srt_name}")

    except asyncio.CancelledError:
        await safe_edit_message(status_msg, "❌ Jarayon bekor qilindi.")
    except Exception as e:
        logger.error(f"Xatolik: {e}", exc_info=True)
        await safe_edit_message(status_msg, f"❌ Xatolik:\n<code>{str(e)}</code>", parse_mode="HTML")
        
    finally:
        context.user_data['is_processing'] = False
        await cleanup_files(video_path, audio_path, srt_path)
