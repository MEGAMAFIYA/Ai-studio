import os
import logging
import xml.sax.saxutils as xml_utils

import aiohttp

from config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION

logger = logging.getLogger(__name__)

TTS_TIMEOUT_SECONDS = 25
AZURE_TTS_URL = f"https://{AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"

# Bular Azure'ning rasmiy o'zbekcha neyron ovozlari — edge-tts ham aynan
# shu ikkalasini (norasmiy yo'l bilan) ishlatgan edi.
UZ_VOICES = ["uz-UZ-SardorNeural", "uz-UZ-MadinaNeural"]


def voice_for_speaker(speaker_label: str, speaker_voice_map: dict) -> str:
    """Har bir noyob spiker yorlig'iga navbat bilan bittadan ovoz biriktiradi."""
    if speaker_label not in speaker_voice_map:
        voice = UZ_VOICES[len(speaker_voice_map) % len(UZ_VOICES)]
        speaker_voice_map[speaker_label] = voice
    return speaker_voice_map[speaker_label]


def _build_ssml(text: str, voice: str) -> str:
    safe_text = xml_utils.escape(text)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="uz-UZ">'
        f'<voice name="{voice}">{safe_text}</voice>'
        '</speak>'
    )


async def synthesize_segment(text: str, voice: str, out_path: str) -> bool:
    """Berilgan matnni Azure Speech (rasmiy) orqali audio faylga aylantiradi."""
    if not text.strip():
        return False

    if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
        logger.error(
            "TTS o'tkazib yuborildi: AZURE_SPEECH_KEY/AZURE_SPEECH_REGION sozlanmagan."
        )
        return False

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
        "User-Agent": "AiStudioBot",
    }
    ssml = _build_ssml(text, voice)

    try:
        timeout = aiohttp.ClientTimeout(total=TTS_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(AZURE_TTS_URL, headers=headers, data=ssml.encode("utf-8")) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Azure TTS xatosi ({voice}): {resp.status} — {body[:300]}")
                    return False
                audio_bytes = await resp.read()

        if not audio_bytes:
            return False

        with open(out_path, "wb") as f:
            f.write(audio_bytes)

        return os.path.exists(out_path) and os.path.getsize(out_path) > 0

    except aiohttp.ClientError as e:
        logger.error(f"Azure TTS tarmoq xatosi ({voice}): {e}")
        return False
    except Exception as e:
        logger.error(f"TTS xatosi ({voice}): {e}", exc_info=True)
        return False
