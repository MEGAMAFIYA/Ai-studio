import asyncio
import logging

from config import HUGGINGFACE_TOKEN

logger = logging.getLogger(__name__)

_pipeline = None
DIARIZATION_TIMEOUT_SECONDS = 300  # birinchi ishga tushishda model yuklanadi, sekinroq


def _get_pipeline():
    """Modelni faqat bir marta, birinchi chaqiriqda yuklaymiz (og'ir ish)."""
    global _pipeline
    if _pipeline is None:
        from pyannote.audio import Pipeline

        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=HUGGINGFACE_TOKEN,
        )
    return _pipeline


def _run_diarization(audio_path: str) -> list:
    """Pyannote'ni ishga tushiradi. Qaytaradi: [(start, end, speaker), ...]"""
    pipeline = _get_pipeline()
    diarization = pipeline(audio_path)
    turns = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append((turn.start, turn.end, speaker))
    return turns


def _assign_speaker(segment: dict, turns: list) -> str:
    """Segment vaqt oralig'iga eng ko'p mos keladigan spikerni tanlaydi."""
    seg_start, seg_end = segment['start'], segment['end']
    best_speaker, best_overlap = None, 0.0
    for start, end, speaker in turns:
        overlap = min(seg_end, end) - max(seg_start, start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker
    return best_speaker or "SPEAKER_00"


async def diarize_segments(audio_path: str, segments: list) -> dict:
    """
    Kim qachon gapirganini pyannote orqali aniqlaydi, so'ng har bir Whisper
    segmentini eng mos spikerga bog'laydi.
    Qaytaradi: {segment_index: "SPEAKER_XX"}
    """
    if not HUGGINGFACE_TOKEN:
        logger.warning("HUGGINGFACE_TOKEN yo'q — diarizatsiya o'tkazib yuborildi.")
        return {i: "SPEAKER_00" for i in range(len(segments))}

    def _run():
        turns = _run_diarization(audio_path)
        return {i: _assign_speaker(seg, turns) for i, seg in enumerate(segments)}

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=DIARIZATION_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.error(
            f"Diarizatsiya {DIARIZATION_TIMEOUT_SECONDS}s ichida tugamadi — "
            f"standart bitta ovozga o'tildi."
        )
        return {i: "SPEAKER_00" for i in range(len(segments))}
    except Exception as e:
        logger.error(f"Diarizatsiya xatosi: {e}", exc_info=True)
        return {i: "SPEAKER_00" for i in range(len(segments))}
