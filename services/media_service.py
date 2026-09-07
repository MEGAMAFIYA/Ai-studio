import os
import asyncio
import logging
import ffmpeg

logger = logging.getLogger(__name__)

async def extract_audio(video_path: str, audio_path: str) -> bool:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video fayl topilmadi: {video_path}")

    logger.info(f"Audio ajratish boshlandi: {video_path}")

    try:
        process = (
            ffmpeg
            .input(video_path)
            .output(
                audio_path,
                vn=None,
                acodec='libopus',
                **{'b:a': '32k'}
            )
            .overwrite_output()
            .get_args()
        )

        proc = await asyncio.create_subprocess_exec(
            'ffmpeg',
            *process[1:],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_message = stderr.decode('utf-8', errors='ignore')
            logger.error(f"FFmpeg xatosi: {error_message}")
            raise RuntimeError("Audio ajratishda FFmpeg xatosi.")

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise RuntimeError("Ajratilgan audio fayl bo'sh.")

        logger.info(f"Audio muvaffaqiyatli ajratildi.")
        return True

    except ffmpeg.Error as e:
        logger.error(f"FFmpeg moduli xatosi: {e.stderr.decode('utf-8') if e.stderr else str(e)}")
        raise RuntimeError("FFmpeg tizimli xatosi.")
    except Exception as e:
        logger.error(f"Kutilmagan xato (extract_audio): {e}", exc_info=True)
        raise
