"""Local faster-whisper inference over the full extracted WAV, with typed millisecond segments."""
import math
import wave
from collections.abc import Callable
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
    speaker: str = "Speaker"


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


_ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "vs.", "etc.", "e.g.", "i.e."}
_TURN_PAIRS = {"and me", "and i", "and my", "i am", "my name", "thank you"}
_TURN_STARTERS = {"i'm", "im", "hello", "hi", "hey"}


def _clean_word(token: str) -> str:
    return token.strip().lower().strip(",.!?;:—-\"'()")


def _join_words(words: list[object]) -> str:
    return "".join(
        w.word if i == 0 or w.word.startswith(" ") else f" {w.word}"
        for i, w in enumerate(words)
    ).strip()


def _split_segment_words(segment: object) -> list[TranscriptSegment]:
    """Split a Whisper segment on pauses, sentences, or turn handoffs using word timestamps."""
    start_ms = seconds_to_milliseconds(segment.start)
    end_ms = seconds_to_milliseconds(segment.end)
    if end_ms < start_ms:
        raise ValueError("Speech segment ends before it starts.")
    words = [w for w in (getattr(segment, "words", None) or []) if getattr(w, "word", "").strip()]
    if not words:
        text = segment.text.strip()
        return [TranscriptSegment(start_ms, end_ms, text)] if text else []

    results: list[TranscriptSegment] = []
    current: list[object] = []
    for index, word in enumerate(words):
        w_start = seconds_to_milliseconds(word.start)
        w_end = seconds_to_milliseconds(word.end)
        if w_end < w_start:
            raise ValueError("Speech word ends before it starts.")
        if current:
            prev = current[-1]
            prev_text = prev.word.strip()
            gap = max(0.0, word.start - prev.end)
            duration = max(0.0, prev.end - current[0].start)
            remaining = max(0.0, words[-1].end - word.start)
            curr_clean = _clean_word(word.word)
            next_clean = _clean_word(words[index + 1].word) if index + 1 < len(words) else ""
            pair = f"{curr_clean} {next_clean}".strip()

            sentence_end = (
                prev_text.endswith((".", "!", "?", "。", "！", "？"))
                and prev_text.lower() not in _ABBREVIATIONS
                and len(prev_text) > 2
                and duration >= 1.2
                and remaining >= 1.0
            )
            pause_split = gap >= 0.80 and duration >= 1.50 and remaining >= 1.0
            handoff_split = (
                (pair in _TURN_PAIRS or curr_clean in _TURN_STARTERS)
                and (
                    (prev_text.endswith((",", ";", ":", "—", "-")) and len(current) >= 2)
                    or (gap >= 0.12 and len(current) >= 3)
                    or len(current) >= 5
                )
            )
            if sentence_end or pause_split or handoff_split:
                text = _join_words(current)
                if text:
                    results.append(TranscriptSegment(
                        seconds_to_milliseconds(current[0].start),
                        seconds_to_milliseconds(current[-1].end),
                        text,
                    ))
                current = []
        current.append(word)

    if current:
        text = _join_words(current)
        if text:
            results.append(TranscriptSegment(
                seconds_to_milliseconds(current[0].start),
                seconds_to_milliseconds(current[-1].end),
                text,
            ))
    return results


def transcribe_audio(
    audio_path: Path, *, model_name: str = "small", device: str = "cpu",
    compute_type: str = "int8", language: str | None = "en", download_root: str,
    cpu_threads: int = 2,
    on_progress: Callable[[int, int], None] | None = None,
) -> TranscriptionResult:
    """Transcribe the whole extracted WAV in one call, so Whisper keeps full context.

    The file is handed to faster-whisper untouched: no slicing, resampling or
    array conversion happens here. Faster-whisper streams its own 30 s windows
    internally. The language is pinned (default "en"; pass None to auto-detect),
    condition_on_previous_text=False stops one bad window from feeding
    hallucinated text into the next, and word_timestamps=True with conversational
    VAD splits multi-speaker turns cleanly. Speaker labels are added afterwards by
    a read-only pass that never changes text or timestamps.
    """
    if cpu_threads < 1:
        raise ValueError("CPU threads must be positive.")
    try:
        with wave.open(str(audio_path), 'rb') as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise SpeechRecognitionError("Extracted audio must be mono 16 kHz PCM WAV.")
            if source.getnframes() <= 0:
                raise SpeechRecognitionError("Extracted audio contains no samples.")
            total_ms = round(source.getnframes() * 1000 / source.getframerate())
        model = load_model(model_name, device, compute_type, download_root, cpu_threads)
        raw_segments, info = model.transcribe(
            str(audio_path), language=language, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200},
            beam_size=5, condition_on_previous_text=False, word_timestamps=True,
        )
        segments: list[TranscriptSegment] = []
        for segment in raw_segments:
            end_ms = seconds_to_milliseconds(segment.end)
            segments.extend(_split_segment_words(segment))
            if on_progress is not None:
                on_progress(min(end_ms, total_ms), total_ms)
        segments.sort(key=lambda segment: (segment.start_ms, segment.end_ms))
        if on_progress is not None:
            on_progress(total_ms, total_ms)
        return TranscriptionResult(language or info.language, segments)
    except SpeechRecognitionError:
        raise
    except Exception as exc:
        raise SpeechRecognitionError("Speech recognition failed. Check the model configuration and recording audio.") from exc
