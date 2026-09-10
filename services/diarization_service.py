import asyncio
import logging
import gc
import os

from config import HUGGINGFACE_TOKEN

logger = logging.getLogger(__name__)

# Render kabi kichik RAMli instansiyalarda PyTorch parallel threadlari RAMni oshirmasin.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

_pipeline = None
_pipeline_load_error = None
DIARIZATION_TIMEOUT_SECONDS = 300  # birinchi ishga tushishda model yuklanadi, sekinroq

TAG = "[DIARIZATSIYA]"


def _get_pipeline():
    """Modelni faqat bir marta, birinchi chaqiriqda yuklaymiz (og'ir ish)."""
    global _pipeline, _pipeline_load_error

    if _pipeline is not None:
        return _pipeline
    if _pipeline_load_error is not None:
        # Oldin ham yuklashga urinib, xato bergan edik — qayta-qayta
        # urinib, loglarni chalkashtirmaslik uchun darhol xato qaytaramiz.
        raise _pipeline_load_error

    logger.info(f"{TAG} pyannote modeli birinchi marta yuklanmoqda (bir necha daqiqa cho'zilishi mumkin)...")
    try:
        from pyannote.audio import Pipeline
        import torch
        torch.set_num_threads(1)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass

        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=HUGGINGFACE_TOKEN,
        )
        logger.info(f"{TAG} model muvaffaqiyatli yuklandi.")
        return _pipeline
    except Exception as e:
        _pipeline_load_error = e
        logger.error(
            f"{TAG} MODEL YUKLANMADI. Eng ehtimoliy sabablar: "
            f"(1) HUGGINGFACE_TOKEN noto'g'ri/eskirgan, "
            f"(2) huggingface.co/pyannote/speaker-diarization-3.1 yoki "
            f"huggingface.co/pyannote/segmentation-3.0 sahifasida "
            f"'Agree and access repository' bosilmagan. Xato: {e}",
            exc_info=True
        )
        raise


def _run_diarization(audio_path: str) -> list:
    """Pyannote'ni ishga tushiradi. Qaytaradi: [(start, end, speaker), ...]"""
    pipeline = _get_pipeline()
    logger.info(f"{TAG} audio tahlil qilinmoqda: {audio_path}")
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
    fallback = {i: "SPEAKER_00" for i in range(len(segments))}

    if not HUGGINGFACE_TOKEN:
        logger.warning(
            f"{TAG} O'TKAZIB YUBORILDI: HUGGINGFACE_TOKEN sozlanmagan. "
            f"Barcha xarakterlar bitta ovozda gapiradi."
        )
        return fallback

    logger.info(f"{TAG} boshlandi ({len(segments)} ta segment uchun spiker aniqlanadi).")

    def _run():
        turns = _run_diarization(audio_path)
        if not turns:
            logger.warning(f"{TAG} model 0 ta nutq segmenti qaytardi (bo'sh natija).")
        result = {i: _assign_speaker(seg, turns) for i, seg in enumerate(segments)}
        unique_speakers = len(set(result.values()))
        logger.info(f"{TAG} yakunlandi: {unique_speakers} ta noyob spiker aniqlandi.")
        # Modelni doimiy RAMda ushlab turmaymiz: Render instansiyasi kichik bo'lsa,
        # job tugagach xotirani qaytarish muhim. Keyingi video kerak bo'lsa qayta yuklanadi.
        global _pipeline
        _pipeline = None
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        return result

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=DIARIZATION_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.error(
            f"{TAG} MUVAFFAQIYATSIZ (TIMEOUT): {DIARIZATION_TIMEOUT_SECONDS}s ichida "
            f"tugamadi — standart bitta ovozga o'tildi."
        )
        return fallback
    except Exception as e:
        logger.error(f"{TAG} MUVAFFAQIYATSIZ (XATO): {e} — standart bitta ovozga o'tildi.")
        return fallback
