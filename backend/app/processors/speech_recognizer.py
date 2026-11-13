"""Reusable local faster-whisper inference with typed millisecond segments."""
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

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
def load_model(model_name: str, device: str, compute_type: str, download_root: str) -> "WhisperModel":
    """Reuse the model within a worker process instead of reloading each recording."""
    try:
        from faster_whisper import WhisperModel
        return WhisperModel(model_name, device=device, compute_type=compute_type,
                            download_root=download_root)
    except Exception as exc:
        raise SpeechRecognitionError("Could not load the speech model. Check model settings and download access.") from exc


def transcribe_audio(
    audio_path: Path, *, model_name: str = "tiny", device: str = "cpu",
    compute_type: str = "int8", language: str | None = None, download_root: str,
) -> TranscriptionResult:
    """Fully consume faster-whisper's iterator before returning a completed result.

    VAD skips silence rather than treating absent speech as a processing failure.
    Automatic language detection is used when no language code is configured.
    """
    model = load_model(model_name, device, compute_type, download_root)
    try:
        raw_segments, info = model.transcribe(str(audio_path), language=language,
                                             vad_filter=True, beam_size=5)
        segments: list[TranscriptSegment] = []
        for segment in raw_segments:
            start_ms = seconds_to_milliseconds(segment.start)
            end_ms = seconds_to_milliseconds(segment.end)
            if end_ms < start_ms:
                raise ValueError("Speech segment ends before it starts.")
            text = segment.text.strip()
            if text:
                segments.append(TranscriptSegment(start_ms, end_ms, text))
        segments.sort(key=lambda segment: (segment.start_ms, segment.end_ms))
        return TranscriptionResult(info.language, segments)
    except Exception as exc:
        raise SpeechRecognitionError("Speech recognition failed. Check the model configuration and recording audio.") from exc
