import os
import re
import shutil
import asyncio
import logging
import aiofiles
from telegram import Message

logger = logging.getLogger(__name__)

def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    if milliseconds >= 1000:
        milliseconds = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


async def create_srt_file(segments: list, output_path: str) -> bool:
    try:
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            for index, segment in enumerate(segments, start=1):
                start_time = format_timestamp(segment['start'])
                end_time = format_timestamp(segment['end'])
                text = segment['text'].strip()
                if not text:
                    continue
                await f.write(f"{index}\n")
                await f.write(f"{start_time} --> {end_time}\n")
                await f.write(f"{text}\n\n")
        return True
    except Exception as e:
        logger.error(f"SRT yaratishda xatolik: {e}", exc_info=True)
        return False


async def cleanup_files(*file_paths: str):
    for path in file_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.error(f"Faylni o'chirishda xatolik ({path}): {e}")


def force_cleanup_temp_dir(temp_dir: str):
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        return

    for filename in os.listdir(temp_dir):
        file_path = os.path.join(temp_dir, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            logger.error(f"Tozalashda xato ({file_path}): {e}")


def get_free_space_mb(path: str = ".") -> float:
    try:
        stat = shutil.disk_usage(path)
        return round(stat.free / (1024 * 1024), 2)
    except Exception as e:
        logger.error(f"Disk hajmini aniqlashda xato: {e}")
        return 0.0


async def safe_edit_message(message: Message, new_text: str, parse_mode: str = None):
    try:
        if message.text != new_text:
            await message.edit_text(new_text, parse_mode=parse_mode)
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            logger.warning(f"Xabarni tahrirlashda xato: {e}")


async def get_media_duration_ms(media_path: str) -> int:
    """ffprobe orqali video/audio faylining davomiyligini millisekundda qaytaradi."""
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', media_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return int(float(stdout.decode().strip()) * 1000)
    except Exception as e:
        logger.error(f"Media davomiyligini aniqlashda xato ({media_path}): {e}")
        return 0


class StepError(Exception):
    """Pipeline bosqichlaridan biri muvaffaqiyatsiz yoki timeout bo'lganda ko'tariladi."""
    def __init__(self, step_name: str, detail: str):
        self.step_name = step_name
        self.detail = detail
        super().__init__(f"{step_name}: {detail}")


async def run_step(coro, step_name: str, timeout_seconds: int):
    """
    Bitta pipeline bosqichini bajaradi: boshlanishi/tugashini logga yozadi,
    va agar u belgilangan vaqtda tugamasa (osilib qolsa) yoki xato bersa,
    aniq StepError bilan to'xtatadi — shunda foydalanuvchi qaysi bosqichda
    va nima sababdan muammo bo'lganini aniq ko'radi.
    """
    logger.info(f"[BOSQICH BOSHLANDI] {step_name}")
    try:
        result = await asyncio.wait_for(coro, timeout=timeout_seconds)
        logger.info(f"[BOSQICH TUGADI] {step_name}")
        return result
    except asyncio.TimeoutError:
        logger.error(f"[BOSQICH OSILIB QOLDI] {step_name} — {timeout_seconds}s ichida javob kelmadi")
        raise StepError(step_name, f"{timeout_seconds} soniyada tugamadi (osilib qoldi)")
    except StepError:
        raise
    except Exception as e:
        logger.error(f"[BOSQICH XATOLIGI] {step_name}: {e}", exc_info=True)
        raise StepError(step_name, str(e))


def sanitize_filename(filename: str) -> str:
    safe_name = re.sub(r'[\\/*?:"<>|]', "_", filename)
    safe_name = safe_name.strip()
    if not safe_name:
        safe_name = "unknown_video"
    return safe_name
