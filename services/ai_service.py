import os
import re
import asyncio
import logging
from groq import AsyncGroq, RateLimitError
from config import GROQ_API_KEY, TEMP_DIR
from utils.helpers import cleanup_files
from services.ai_providers import iter_available_providers, call_chat_completion, PROVIDERS

logger = logging.getLogger(__name__)

groq_client = AsyncGroq(api_key=GROQ_API_KEY)
MAX_CHUNK_SIZE_BYTES = 24 * 1024 * 1024

async def split_audio_if_needed(audio_path: str) -> list:
    file_size = os.path.getsize(audio_path)
    
    if file_size <= MAX_CHUNK_SIZE_BYTES:
        return [audio_path]

    logger.warning(f"Audio hajmi limitdan oshdi. Bo'laklash boshlandi...")
    
    try:
        probe_cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', audio_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *probe_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        total_duration = float(stdout.decode().strip())
    except Exception as e:
        logger.error(f"Audio davomiyligini aniqlashda xato: {e}")
        raise RuntimeError("Audio davomiyligini o'qib bo'lmadi.")

    num_chunks = int(file_size / MAX_CHUNK_SIZE_BYTES) + 1
    chunk_duration = total_duration / num_chunks
    chunk_paths = []
    base_name = os.path.splitext(os.path.basename(audio_path))[0]

    for i in range(num_chunks):
        start_time = i * chunk_duration
        chunk_path = os.path.join(TEMP_DIR, f"{base_name}_chunk_{i}.ogg")
        
        cmd = [
            'ffmpeg', '-y', '-i', audio_path,
            '-ss', str(start_time), '-t', str(chunk_duration),
            '-c', 'copy', chunk_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        if os.path.exists(chunk_path):
            chunk_paths.append((chunk_path, start_time))
            
    return chunk_paths


async def transcribe_audio(audio_path: str) -> list:
    if not os.path.exists(audio_path):
        return []

    segments = []
    chunks = []
    is_chunked = False
    
    try:
        chunks = await split_audio_if_needed(audio_path)
        is_chunked = isinstance(chunks[0], tuple)
        
        for chunk_data in chunks:
            if is_chunked:
                chunk_path, time_offset = chunk_data
            else:
                chunk_path = chunk_data
                time_offset = 0.0

            max_retries = 3
            retry_delay = 10
            
            for attempt in range(max_retries):
                try:
                    with open(chunk_path, "rb") as file:
                        transcription = await groq_client.audio.transcriptions.create(
                            file=(os.path.basename(chunk_path), file.read()),
                            model="whisper-large-v3",
                            response_format="verbose_json"
                        )
                    break
                except RateLimitError:
                    if attempt < max_retries - 1:
                        logger.warning(f"STT Rate limit! {retry_delay}s kutilmoqda...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        raise RuntimeError("Bepul API limiti tugadi.")
            
            if hasattr(transcription, 'segments') and transcription.segments:
                for seg in transcription.segments:
                    segments.append({
                        'start': float(seg['start']) + time_offset,
                        'end': float(seg['end']) + time_offset,
                        'text': seg['text'].strip()
                    })
            
            if is_chunked:
                await cleanup_files(chunk_path)

        return segments

    except Exception as e:
        logger.error(f"Groq STT xatosi: {e}", exc_info=True)
        if is_chunked:
            for chunk_data in chunks:
                await cleanup_files(chunk_data[0])
        return []


async def translate_text_to_uzbek(segments: list) -> list:
    if not segments:
        return []

    translated_segments = []
    chunk_size = 15

    for i in range(0, len(segments), chunk_size):
        chunk = segments[i:i + chunk_size]

        texts_to_translate = [seg['text'] for seg in chunk]
        numbered_text = "\n".join([f"{idx+1}. {txt}" for idx, txt in enumerate(texts_to_translate)])

        prompt = (
            "Sen professional kino tarjimonisan. Quyidagi raqamlangan matnlarni o'zbek tiliga tabiiy va ravon tarjima qil.\n"
            "Qoidalar:\n"
            "- Har bir qatorni xuddi shunday raqam bilan boshla (1., 2., 3...).\n"
            "- Har bir raqam faqat BITTA qatorda, ketma-ket, bo'lib-bo'lib yozilmasdan bo'lsin.\n"
            "- Nechta matn berilsa, aynan shuncha qator qaytar — birortasini ham tashlab ketma yoki birlashtirma.\n"
            "- Faqat tarjimani qaytar, ortiqcha izoh yozma.\n"
            "- Kino dialoglariga mos uslubda tarjima qil.\n\n"
            f"Matnlar:\n{numbered_text}"
        )

        messages = [
            {"role": "system", "content": "You are a highly skilled Uzbek translator for movies. Output only the translated numbered list."},
            {"role": "user", "content": prompt}
        ]

        response_text = None
        last_error = None

        # Bir provayder/kalit ishlamasa (limit, xato, deprecated model),
        # ro'yxatdagi keyingisiga avtomatik o'tiladi.
        for provider_id, api_key in iter_available_providers():
            try:
                # max_tokens standart (2048) ba'zan 15 qatorlik uzun dialoglar
                # uchun yetmay, javob yarmida kesilib qolardi — natijada oxirgi
                # qatorlar "tarjima qilinmagan" holda asl tilda qolib ketardi.
                response_text = await call_chat_completion(
                    provider_id, api_key, messages, max_tokens=4096
                )
                break
            except Exception as e:
                last_error = e
                label = PROVIDERS[provider_id]["label"]
                logger.warning(f"[Tarjima] {label} ishlamadi ({i // chunk_size + 1}-bo'lak): {e}")
                continue

        if response_text is None:
            logger.error(f"[Tarjima] Barcha provayderlar ishlamadi ({i // chunk_size + 1}-bo'lak): {last_error}")
            for seg in chunk:
                error_seg = seg.copy()
                error_seg['text'] = seg['text'] + " [Tarjima xatosi]"
                translated_segments.append(error_seg)
            continue

        chunk_texts = _parse_numbered_translation(response_text, len(chunk))

        for j, original_seg in enumerate(chunk):
            new_segment = original_seg.copy()
            matched_text = chunk_texts.get(j)

            if not matched_text:
                logger.warning(
                    f"[Tarjima] {i // chunk_size + 1}-bo'lak, {j+1}-qator mos kelmadi — "
                    f"asl matn saqlanib qolindi: {original_seg['text'][:60]!r}"
                )

            new_segment['text'] = matched_text if matched_text else original_seg['text']
            translated_segments.append(new_segment)

    return translated_segments


_NUMBERED_LINE_RE = re.compile(r'^\s*(\d+)\s*[\.\)\:\-]\s*(.*)$')


def _parse_numbered_translation(response_text: str, expected_count: int) -> dict:
    """
    Modelning "1. tarjima" ko'rinishidagi javobini {0-based index: matn} qilib ajratadi.

    Model har doim ham talab qilingan "1." formatida javob bermaydi (masalan "1)"
    yozishi, ba'zi qatorlarni qo'shib yuborishi yoki raqamlarni chalkashtirishi mumkin).
    Avval raqam bo'yicha moslashga harakat qilinadi; agar bu yetarlicha mos kelmasa,
    qatorlar soni kutilganga teng bo'lsa tartib bo'yicha (pozitsion) moslashtiriladi —
    shunda hech qanday qator "tarjima qilinmagan holda" asl tildan qolib ketmaydi.
    """
    raw_lines = [ln.strip() for ln in response_text.split('\n') if ln.strip()]

    by_number = {}
    for line in raw_lines:
        m = _NUMBERED_LINE_RE.match(line)
        if not m:
            continue
        num = int(m.group(1))
        text = m.group(2).strip()
        if 1 <= num <= expected_count and text:
            # Agar bir xil raqam ikki marta uchrasa, birinchisini saqlaymiz.
            by_number.setdefault(num - 1, text)

    if len(by_number) >= expected_count:
        return by_number

    # Raqam bo'yicha moslashtirish to'liq bo'lmadi (masalan model "1)" yoki
    # raqamsiz ro'yxat qaytargan). Qatorlar soni to'g'ri kelsa, tartib bo'yicha
    # (index bo'yicha) moslashtiramiz — bu ko'pincha to'g'ri natija beradi.
    stripped_lines = [_NUMBERED_LINE_RE.sub(r'\2', ln).strip() or ln for ln in raw_lines]
    if len(stripped_lines) == expected_count:
        return {idx: text for idx, text in enumerate(stripped_lines)}

    # Ikkalasi ham mos kelmasa, faqat raqam orqali topilganlarni qaytaramiz —
    # qolganlari chaqiruvchi tomonidan asl matn bilan to'ldiriladi.
    return by_number
