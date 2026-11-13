"""Local FFprobe validation and FFmpeg conversion, independent of HTTP and SQL."""
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaProcessingError(ValueError):
    """A safe message describing unreadable media or failed audio extraction."""


class MediaToolUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoMetadata:
    duration_ms: int


def run_media_command(arguments: list[str], timeout: int) -> str:
    """Run a local tool without a shell; stderr may contain private file details."""
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=True)
        return result.stdout
    except FileNotFoundError as exc:
        raise MediaToolUnavailableError("FFmpeg/FFprobe is not installed or configured.") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProcessingError("Media processing exceeded its time limit.") from exc
    except subprocess.CalledProcessError as exc:
        raise MediaProcessingError("The media tool could not read or convert this recording.") from exc


def validate_video(video_path: Path, ffprobe: str = "ffprobe", timeout: int = 120) -> VideoMetadata:
    """Require an MP4 container with real video, audio, and a finite duration."""
    output = run_media_command([
        ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
        "-show_entries", "format=format_name,duration:stream=codec_type",
        "-of", "json", str(video_path),
    ], timeout)
    try:
        metadata = json.loads(output)
        formats = metadata["format"]["format_name"].split(",")
        streams = {stream["codec_type"] for stream in metadata["streams"]}
        duration = float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaProcessingError("The recording has invalid or unreadable media metadata.") from exc
    if "mp4" not in formats or "video" not in streams:
        raise MediaProcessingError("Upload a valid MP4 containing a video stream.")
    if "audio" not in streams:
        raise MediaProcessingError("This recording has no audio stream to transcribe.")
    if not math.isfinite(duration) or duration <= 0:
        raise MediaProcessingError("The recording has no readable duration.")
    return VideoMetadata(round(duration * 1000))


def extract_audio(video_path: Path, output_path: Path, ffmpeg: str = "ffmpeg", timeout: int = 3600) -> Path:
    """Decode the first audio stream to mono 16 kHz WAV for speech recognition.

    Explicit stream mapping rejects missing audio; local-only protocols prevent
    uploaded container metadata from being used to fetch remote resources.
    """
    run_media_command([
        ffmpeg, "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file,pipe",
        "-i", str(video_path), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(output_path),
    ], timeout)
    if not output_path.is_file() or output_path.stat().st_size <= 44:
        raise MediaProcessingError("Audio extraction produced no readable audio.")
    return output_path
