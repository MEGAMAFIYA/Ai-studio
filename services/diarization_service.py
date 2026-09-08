import asyncio
import logging

import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav
from sklearn.cluster import AgglomerativeClustering

logger = logging.getLogger(__name__)

_encoder = None

# Bir xil odamning ikkita gapi orasidagi kosinus masofasi odatda shundan
# past bo'ladi. Kattaroq qiymat = kamroq spiker (ovozlarni ko'proq
# birlashtiradi), kichikroq qiymat = ko'proq spiker (nozikroq ajratadi).
CLUSTER_DISTANCE_THRESHOLD = 0.35
MIN_SEGMENT_SECONDS = 0.3
DIARIZATION_TIMEOUT_SECONDS = 180


def _get_encoder():
    """Modelni faqat bir marta, birinchi chaqiriqda yuklaymiz (og'ir ish)."""
    global _encoder
    if _encoder is None:
        _encoder = VoiceEncoder()
    return _encoder


async def diarize_segments(audio_path: str, segments: list) -> dict:
    """
    HF token yoki gated model kerak emas: Resemblyzer o'z vaznlarini o'zi
    bilan olib yuradi. Har bir Whisper segmentidan ovoz "barmoq izi"ni
    (embedding) chiqarib, ularni klasterlashtirib, kim kimligini taxmin
    qiladi.

    Qaytaradi: {segment_index: "SPEAKER_XX"}
    """

    def _run():
        encoder = _get_encoder()
        wav = preprocess_wav(audio_path)
        sr = 16000  # resemblyzer ichida shu chastotaga normallashtiradi

        embeddings, valid_indices = [], []

        for i, seg in enumerate(segments):
            start_sample = int(seg['start'] * sr)
            end_sample = int(seg['end'] * sr)
            chunk = wav[start_sample:end_sample]

            if len(chunk) < sr * MIN_SEGMENT_SECONDS:
                continue  # juda qisqa segment — ishonchli ovoz izi chiqmaydi

            embeddings.append(encoder.embed_utterance(chunk))
            valid_indices.append(i)

        if len(embeddings) < 2:
            return {i: "SPEAKER_00" for i in range(len(segments))}

        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=CLUSTER_DISTANCE_THRESHOLD,
            metric='cosine',
            linkage='average',
        )
        labels = clustering.fit_predict(np.array(embeddings))

        result = {idx: f"SPEAKER_{label:02d}" for idx, label in zip(valid_indices, labels)}

        # Ovoz izi chiqmagan (juda qisqa) segmentlarga eng yaqin oldingi
        # segmentning spikerini beramiz — bo'sh qoldirmaslik uchun.
        last_known = "SPEAKER_00"
        for i in range(len(segments)):
            if i in result:
                last_known = result[i]
            else:
                result[i] = last_known

        return result

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=DIARIZATION_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.error(
            f"Diarizatsiya {DIARIZATION_TIMEOUT_SECONDS}s ichida tugamadi — "
            f"standart bitta ovozga o'tildi. (Fon jarayoni baribir davom etadi, "
            f"lekin natijasi endi ishlatilmaydi.)"
        )
        return {i: "SPEAKER_00" for i in range(len(segments))}
    except Exception as e:
        logger.error(f"Diarizatsiya xatosi: {e}", exc_info=True)
        return {i: "SPEAKER_00" for i in range(len(segments))}
