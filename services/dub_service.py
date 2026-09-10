import os
import asyncio
import logging
import subprocess

from config import TEMP_DIR
from utils.helpers import cleanup_files, get_media_duration_ms
from services.tts_service import synthesize_segment, voice_for_speaker
from services.diarization_service import diarize_segments

logger = logging.getLogger(__name__)

MIN_TEMPO, MAX_TEMPO = 0.75, 1.6
ORIGINAL_VOLUME_REDUCTION_DB = 15


async def _ffprobe_duration_ms(path: str) -> int:
    """Audio durationini RAMga faylni yuklamasdan aniqlaydi."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return 0
    try:
        return int(float(stdout.decode().strip()) * 1000)
    except (ValueError, TypeError):
        return 0


async def _fit_duration(clip_path: str, target_ms: int) -> str:
    """TTS klipini kerakli davomiylikka moslaydi; pydub/PCM RAM ishlatilmaydi."""
    if target_ms <= 0 or not os.path.exists(clip_path):
        return clip_path

    current_ms = await _ffprobe_duration_ms(clip_path)
    if current_ms <= 0:
        return clip_path

    tempo = max(MIN_TEMPO, min(MAX_TEMPO, current_ms / target_ms))
    if abs(tempo - 1.0) < 0.03:
        return clip_path

    fitted_path = clip_path.rsplit(".", 1)[0] + "_fit.mp3"
    cmd = ["ffmpeg", "-y", "-i", clip_path, "-filter:a", f"atempo={tempo}", fitted_path]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await proc.communicate()
    return fitted_path if proc.returncode == 0 and os.path.exists(fitted_path) else clip_path


async def _mix_with_ffmpeg(video_path: str, audio_path: str, clips: list, output_path: str, total_duration_ms: int) -> bool:
    """Barcha audio qatlamlarini ffmpeg orqali oqim tarzida aralashtiradi.

    Eski pydub overlay usuli butun trekni PCM sifatida RAMga yuklardi.
    Bu usul esa disk/ffmpeg oqimidan foydalanib, RAM sarfini ancha kamaytiradi.
    """
    if not clips:
        # TTS kliplari bo'lmasa ham asl audio pasaytirilgan holda chiqadi.
        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-af", f"volume=-{ORIGINAL_VOLUME_REDUCTION_DB}dB",
            "-t", str(total_duration_ms / 1000), "-c:a", "pcm_s16le", output_path,
        ]
    else:
        cmd = ["ffmpeg", "-y", "-i", audio_path]
        for clip_path, start_ms in clips:
            cmd += ["-i", clip_path]

        filter_parts = [f"[0:a]volume=-{ORIGINAL_VOLUME_REDUCTION_DB}dB[orig]"]
        labels = ["[orig]"]
        for idx, (_, start_ms) in enumerate(clips, start=1):
            # adelay har kanal uchun bir xil kechikish: audio 1 kanalga majburlanadi.
            filter_parts.append(
                f"[{idx}:a]aformat=channel_layouts=mono,adelay={max(0, int(start_ms))}|{max(0, int(start_ms))}[d{idx}]"
            )
            labels.append(f"[d{idx}]")

        filter_parts.append(
            "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0[mix]"
        )
        filter_complex = ";".join(filter_parts)
        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[mix]", "-t", str(total_duration_ms / 1000),
            "-c:a", "pcm_s16le", output_path,
        ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not os.path.exists(output_path):
        logger.error("Audio mixing xatosi: %s", stderr.decode("utf-8", errors="ignore")[-1500:])
        return False
    return True


async def build_dubbed_audio(video_path: str, audio_path: str, translated_segments: list, base_name: str) -> str:
    """Diarizatsiya + Azure TTS + RAM-tejamkor ffmpeg mixing."""
    speaker_map = await diarize_segments(audio_path, translated_segments)
    speaker_voice_map = {}

    total_duration_ms = await get_media_duration_ms(video_path)
    if total_duration_ms <= 0:
        logger.error("Video davomiyligini aniqlab bo'lmadi, dublyaj to'xtatildi.")
        return None

    temp_files = []
    clips = []
    total_segments = len(translated_segments)

    try:
        for i, seg in enumerate(translated_segments):
            text = (seg.get("text") or "").strip()
            if not text:
                continue

            speaker = speaker_map.get(i, "SPEAKER_00")
            voice = voice_for_speaker(speaker, speaker_voice_map)
            logger.info("[Dublyaj] segment %s/%s (%s) sintez qilinmoqda...", i + 1, total_segments, voice)

            raw_clip = os.path.join(TEMP_DIR, f"{base_name}_seg{i}.mp3")
            ok = await synthesize_segment(text, voice, raw_clip)
            if not ok:
                logger.warning("[Dublyaj] segment %s/%s o'tkazib yuborildi (TTS muvaffaqiyatsiz)", i + 1, total_segments)
                continue
            temp_files.append(raw_clip)

            target_ms = int((seg["end"] - seg["start"]) * 1000)
            fitted_clip = await _fit_duration(raw_clip, target_ms)
            if fitted_clip != raw_clip:
                temp_files.append(fitted_clip)

            if os.path.exists(fitted_clip):
                clips.append((fitted_clip, max(0, int(seg["start"] * 1000))))

        mixed_path = os.path.join(TEMP_DIR, f"{base_name}_dubbed_audio.wav")
        ok = await _mix_with_ffmpeg(video_path, audio_path, clips, mixed_path, total_duration_ms)
        if not ok:
            return None
        return mixed_path
    finally:
        await cleanup_files(*temp_files)
