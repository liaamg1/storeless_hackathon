"""Local inference over bounded WAV windows, with timestamps in the original recording."""
import math
import wave
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

class SpeechRecognitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    language: str
    segments: list[TranscriptSegment]


def seconds_to_milliseconds(seconds: float) -> int:
    """Round model seconds to the integer millisecond format stored in PostgreSQL."""
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Speech timestamps must be finite and nonnegative.")
    return round(seconds * 1000)


@lru_cache(maxsize=1)
def load_model(model_name: str, device: str, compute_type: str, download_root: str,
               cpu_threads: int = 2) -> "WhisperModel":
    """Reuse one model; leave CPU capacity for the API, database and desktop."""
    try:
        from faster_whisper import WhisperModel
        return WhisperModel(model_name, device=device, compute_type=compute_type,
                            download_root=download_root, cpu_threads=cpu_threads, num_workers=1)
    except Exception as exc:
        raise SpeechRecognitionError("Could not load the speech model. Check model settings and download access.") from exc


def transcribe_audio(
    audio_path: Path, *, model_name: str = "small", device: str = "cpu",
    compute_type: str = "int8", language: str | None = None, download_root: str,
    chunk_seconds: int = 60, cpu_threads: int = 2,
    on_progress: Callable[[int, int], None] | None = None,
) -> TranscriptionResult:
    """Keep audio, VAD and feature buffers bounded even for multi-hour recordings.

    Read the extracted mono 16 kHz PCM WAV directly rather than asking Whisper to
    decode the entire file. Two seconds of surrounding audio help with words at a
    boundary; midpoint ownership emits context segments in only one window.
    Only the much smaller transcript text accumulates for atomic persistence.
    """
    if not 1 <= chunk_seconds <= 120 or cpu_threads < 1:
        raise ValueError("Chunk duration must be 1–120 seconds and CPU threads must be positive.")
    try:
        with wave.open(str(audio_path), 'rb') as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise SpeechRecognitionError("Extracted audio must be mono 16 kHz PCM WAV.")
            sample_rate = source.getframerate()
            total_frames = source.getnframes()
            if total_frames <= 0:
                raise SpeechRecognitionError("Extracted audio contains no samples.")
            total_ms = round(total_frames * 1000 / sample_rate)
            chunk_frames = chunk_seconds * sample_rate
            context_frames = min(2 * sample_rate, chunk_frames // 2)
            model = load_model(model_name, device, compute_type, download_root, cpu_threads)
            segments: list[TranscriptSegment] = []
            languages: Counter[str] = Counter()
            detected_language = language or 'en'
            for core_start in range(0, total_frames, chunk_frames):
                core_end = min(core_start + chunk_frames, total_frames)
                start_ms = round(core_start * 1000 / sample_rate)
                end_ms = round(core_end * 1000 / sample_rate)
                read_start = max(0, core_start - context_frames)
                read_end = min(total_frames, core_end + context_frames)
                source.setpos(read_start)
                pcm = source.readframes(read_end - read_start)
                if len(pcm) != (read_end - read_start) * 2:
                    raise SpeechRecognitionError("Extracted audio is incomplete or truncated.")
                audio = np.frombuffer(pcm, dtype='<i2').astype(np.float32)
                audio /= 32768.0
                # Passing an array bypasses Faster Whisper's full-file decoder.
                raw_segments, info = model.transcribe(audio, language=language, vad_filter=True, beam_size=5)
                detected_language = info.language
                offset_ms = round(read_start * 1000 / sample_rate)
                for segment in raw_segments:
                    start = offset_ms + seconds_to_milliseconds(segment.start)
                    end = offset_ms + seconds_to_milliseconds(segment.end)
                    if end < start:
                        raise ValueError("Speech segment ends before it starts.")
                    text = segment.text.strip()
                    if text and start_ms <= (start + end) / 2 < end_ms:
                        segments.append(TranscriptSegment(max(0, start), min(total_ms, end), text))
                        languages[info.language] += max(1, end - start)
                # The exhausted generator must not keep an old window alive while
                # the next window's feature/VAD buffers are allocated.
                del raw_segments, audio, pcm
                if on_progress is not None:
                    on_progress(end_ms, total_ms)
            segments.sort(key=lambda segment: (segment.start_ms, segment.end_ms))
            result_language = language or (languages.most_common(1)[0][0] if languages else detected_language)
            return TranscriptionResult(result_language, segments)
    except SpeechRecognitionError:
        raise
    except Exception as exc:
        raise SpeechRecognitionError("Speech recognition failed. Check the model configuration and recording audio.") from exc
