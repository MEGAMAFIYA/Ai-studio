import os
import asyncio
import logging

from pydub import AudioSegment

from config import TEMP_DIR
from utils.helpers import cleanup_files, get_media_duration_ms
from services.tts_service import synthesize_segment, voice_for_speaker
from services.diarization_service import diarize_segments

logger = logging.getLogger(__name__)

# ffmpeg atempo filtri 0.5-2.0 oralig'ida ishonchli ishlaydi.
MIN_TEMPO, MAX_TEMPO = 0.75, 1.6
ORIGINAL_VOLUME_REDUCTION_DB = 15  # asl ovozni shuncha dB pasaytiramiz


async def _fit_duration(clip_path: str, target_ms: int) -> str:
    """TTS klipini asl segment davomiyligiga imkon qadar moslashtiradi (tezlik o'zgartirib)."""
    try:
        clip = AudioSegment.from_file(clip_path)
    except Exception:
        return clip_path

    current_ms = len(clip)
    if current_ms == 0 or target_ms <= 0:
        return clip_path

    tempo = max(MIN_TEMPO, min(MAX_TEMPO, current_ms / target_ms))
    if abs(tempo - 1.0) < 0.03:
        return clip_path

    fitted_path = clip_path.rsplit(".", 1)[0] + "_fit.mp3"
    cmd = ['ffmpeg', '-y', '-i', clip_path, '-filter:a', f'atempo={tempo}', fitted_path]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await proc.communicate()
    return fitted_path if os.path.exists(fitted_path) else clip_path


async def build_dubbed_audio(video_path: str, audio_path: str, translated_segments: list, base_name: str) -> str:
    """
    1. Asl audioni diarizatsiya qiladi (kim qachon gapirgani).
    2. Har bir tarjima segmentini mos spikerning ovozida TTS qiladi.
    3. Har bir klipni jim (silent) yo'lakka o'z vaqtida joylaydi.
    4. Shu dublyaj yo'lagini asl audio (pasaytirilgan) bilan birlashtiradi.
    Yakuniy aralashtirilgan audio fayl yo'lini qaytaradi, muvaffaqiyatsiz bo'lsa None.
    """
    speaker_map = await diarize_segments(audio_path, translated_segments)
    speaker_voice_map = {}

    total_duration_ms = await get_media_duration_ms(video_path)
    if total_duration_ms <= 0:
        logger.error("Video davomiyligini aniqlab bo'lmadi, dublyaj to'xtatildi.")
        return None

    dub_track = AudioSegment.silent(duration=total_duration_ms)
    temp_files = []

    for i, seg in enumerate(translated_segments):
        text = (seg.get('text') or "").strip()
        if not text:
            continue

        speaker = speaker_map.get(i, "SPEAKER_00")
        voice = voice_for_speaker(speaker, speaker_voice_map)

        raw_clip = os.path.join(TEMP_DIR, f"{base_name}_seg{i}.mp3")
        ok = await synthesize_segment(text, voice, raw_clip)
        if not ok:
            continue
        temp_files.append(raw_clip)

        target_ms = int((seg['end'] - seg['start']) * 1000)
        fitted_clip = await _fit_duration(raw_clip, target_ms)
        if fitted_clip != raw_clip:
            temp_files.append(fitted_clip)

        try:
            clip_audio = AudioSegment.from_file(fitted_clip)
            start_ms = max(0, int(seg['start'] * 1000))
            dub_track = dub_track.overlay(clip_audio, position=start_ms)
        except Exception as e:
            logger.error(f"Segment #{i} ni yo'lakka joylashda xato: {e}")

    await cleanup_files(*temp_files)

    try:
        original = AudioSegment.from_file(audio_path) - ORIGINAL_VOLUME_REDUCTION_DB
    except Exception as e:
        logger.error(f"Asl audioni o'qishda xato: {e}")
        original = AudioSegment.silent(duration=total_duration_ms)

    final_len = max(len(original), len(dub_track), total_duration_ms)
    mixed = AudioSegment.silent(duration=final_len).overlay(original).overlay(dub_track)

    mixed_path = os.path.join(TEMP_DIR, f"{base_name}_dubbed_audio.wav")
    mixed.export(mixed_path, format="wav")

    return mixed_path
