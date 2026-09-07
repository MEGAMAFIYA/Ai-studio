import os
import asyncio
import logging
from groq import AsyncGroq, RateLimitError
from config import GROQ_API_KEY, TEMP_DIR
from utils.helpers import cleanup_files

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
            "- Faqat tarjimani qaytar, ortiqcha izoh yozma.\n"
            "- Kino dialoglariga mos uslubda tarjima qil.\n\n"
            f"Matnlar:\n{numbered_text}"
        )

        max_retries = 3
        retry_delay = 10
        
        for attempt in range(max_retries):
            try:
                chat_completion = await groq_client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a highly skilled Uzbek translator for movies. Output only the translated numbered list."},
                        {"role": "user", "content": prompt}
                    ],
                    model="llama3-8b-8192",
                    temperature=0.3,
                    max_tokens=2048
                )
                
                response_text = chat_completion.choices[0].message.content.strip()
                translated_lines = response_text.split('\n')
                
                for j, original_seg in enumerate(chunk):
                    new_segment = original_seg.copy()
                    matched_text = None
                    expected_prefix = f"{j+1}."
                    
                    for line in translated_lines:
                        clean_line = line.strip()
                        if clean_line.startswith(expected_prefix):
                            matched_text = clean_line[len(expected_prefix):].strip()
                            break
                    
                    if matched_text:
                        new_segment['text'] = matched_text
                    else:
                        new_segment['text'] = original_seg['text']
                        
                    translated_segments.append(new_segment)
                break
                
            except RateLimitError:
                if attempt < max_retries - 1:
                    logger.warning(f"LLM Rate limit! {retry_delay}s kutilmoqda...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    for seg in chunk:
                        error_seg = seg.copy()
                        error_seg['text'] = seg['text'] + " [Limit]"
                        translated_segments.append(error_seg)
            except Exception as e:
                logger.error(f"Tarjima xatosi: {e}")
                for seg in chunk:
                    error_seg = seg.copy()
                    error_seg['text'] = seg['text']
                    translated_segments.append(error_seg)
                break

    return translated_segments
