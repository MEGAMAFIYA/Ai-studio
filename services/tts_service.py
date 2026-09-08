import os
import logging
import asyncio

import edge_tts

logger = logging.getLogger(__name__)

# edge-tts o'zida timeout yo'q — tarmoq muammosi bo'lsa abadiy osilib qoladi.
# Shuning uchun har bir chaqiruvni o'zimiz cheklaymiz.
TTS_TIMEOUT_SECONDS = 25

# DIQQAT: Bepul manbalarda (Microsoft Edge-TTS) o'zbek tilida hozircha
# faqat SHU IKKITA tabiiy ovoz mavjud. "Ko'p xarakter" degani aslida shu
# ikkitasi orasida spikerlarga qarab almashtirib berish, cheksiz turli
# ovozlar emas. Haqiqiy noyob ovozlar kerak bo'lsa, pullik xizmat
# (masalan ElevenLabs voice cloning) kerak bo'ladi va sifat kafolatlanmaydi,
# chunki ular o'zbek tilini "tug'ma" qo'llab-quvvatlamaydi.
UZ_VOICES = ["uz-UZ-SardorNeural", "uz-UZ-MadinaNeural"]


def voice_for_speaker(speaker_label: str, speaker_voice_map: dict) -> str:
    """Har bir noyob spiker yorlig'iga navbat bilan bittadan ovoz biriktiradi."""
    if speaker_label not in speaker_voice_map:
        voice = UZ_VOICES[len(speaker_voice_map) % len(UZ_VOICES)]
        speaker_voice_map[speaker_label] = voice
    return speaker_voice_map[speaker_label]


async def synthesize_segment(text: str, voice: str, out_path: str) -> bool:
    """Berilgan matnni berilgan ovozda audio faylga aylantiradi."""
    if not text.strip():
        return False
    try:
        communicate = edge_tts.Communicate(text, voice)
        await asyncio.wait_for(communicate.save(out_path), timeout=TTS_TIMEOUT_SECONDS)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except asyncio.TimeoutError:
        logger.error(
            f"TTS vaqti tugadi ({voice}, {TTS_TIMEOUT_SECONDS}s): "
            f"'{text[:40]}...' — server javob bermadi, segment o'tkazib yuborildi."
        )
        return False
    except Exception as e:
        logger.error(f"TTS xatosi ({voice}): {e}", exc_info=True)
        return False
