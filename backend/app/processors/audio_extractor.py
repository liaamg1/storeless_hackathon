"""Local FFprobe validation, keyframe MP4 segmentation, and FFmpeg audio conversion."""
from concurrent.futures import ThreadPoolExecutor
import csv
import json
import math
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path


class MediaProcessingError(ValueError):
    """A safe message describing unreadable media or failed audio extraction."""


class MediaToolUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoMetadata:
    duration_ms: int


@dataclass(frozen=True)
class VideoSegment:
    path: Path
    start_ms: int
    end_ms: int


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


def split_video_segments(
    video_path: Path,
    output_dir: Path,
    duration_ms: int,
    *,
    parts: int = 4,
    ffmpeg: str = "ffmpeg",
    timeout: int = 3600,
) -> list[VideoSegment]:
    """Split an MP4 on keyframes by time via `ffmpeg -f segment -segment_time <duration/parts> -c copy`.

    Never slice an MP4 by raw byte offsets, which destroys the MP4 container header
    (moov atom) and produces unreadable chunks. Stream copy (-c copy) splits on keyframes
    into valid standalone MP4 files without re-encoding.
    """
    if duration_ms <= 0 or parts < 1:
        raise ValueError("duration_ms and parts must be positive.")
    output_dir.mkdir(parents=True, exist_ok=True)
    segment_seconds = max(0.5, (duration_ms / 1000.0) / parts)
    segment_time_arg = f"{segment_seconds:.3f}".rstrip("0").rstrip(".")
    list_path = output_dir / "segments.csv"
    pattern = output_dir / "segment_%03d.mp4"
    run_media_command([
        ffmpeg,
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(video_path),
        "-f",
        "segment",
        "-segment_time",
        segment_time_arg,
        "-c",
        "copy",
        "-reset_timestamps",
        "1",
        "-segment_list",
        str(list_path),
        "-segment_list_type",
        "csv",
        str(pattern),
    ], timeout)

    segments: list[VideoSegment] = []
    if list_path.is_file():
        with list_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if len(row) < 3:
                    continue
                seg_path = output_dir / Path(row[0]).name
                if not seg_path.is_file() or seg_path.stat().st_size <= 0:
                    continue
                try:
                    start_ms = max(0, round(float(row[1]) * 1000))
                    end_ms = max(start_ms, round(float(row[2]) * 1000))
                except ValueError as exc:
                    raise MediaProcessingError("Invalid segment timestamp metadata produced by FFmpeg.") from exc
                segments.append(VideoSegment(seg_path, start_ms, end_ms))

    if not segments:
        files = [
            path
            for path in sorted(output_dir.glob("segment_*.mp4"))
            if path.is_file() and path.stat().st_size > 0
        ]
        if not files:
            raise MediaProcessingError("Video segmentation produced no readable MP4 segments.")
        step_ms = duration_ms / len(files)
        for index, seg_path in enumerate(files):
            start_ms = round(index * step_ms)
            end_ms = duration_ms if index == len(files) - 1 else round((index + 1) * step_ms)
            segments.append(VideoSegment(seg_path, start_ms, end_ms))

    return segments


def extract_audio(video_path: Path, output_path: Path, ffmpeg: str = "ffmpeg", timeout: int = 3600) -> Path:
    """Decode the first audio stream to mono 16 kHz WAV for speech recognition.

    Explicit stream mapping rejects missing audio; local-only protocols prevent
    uploaded container metadata from being used to fetch remote resources.
    """
    run_media_command([
        ffmpeg, "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file,pipe",
        "-threads", "1", "-i", str(video_path), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(output_path),
    ], timeout)
    if not output_path.is_file() or output_path.stat().st_size <= 44:
        raise MediaProcessingError("Audio extraction produced no readable audio.")
    return output_path


def extract_segmented_audio(
    video_path: Path,
    output_path: Path,
    ffmpeg: str = "ffmpeg",
    timeout: int = 3600,
    *,
    duration_ms: int,
    parts: int = 4,
) -> Path:
    """Split a large MP4 on keyframes via `-f segment -c copy` and extract audio in parallel."""
    segments_dir = output_path.parent / "mp4_segments"
    try:
        segments = split_video_segments(
            video_path,
            segments_dir,
            duration_ms,
            parts=parts,
            ffmpeg=ffmpeg,
            timeout=timeout,
        )
        part_wavs = [segments_dir / f"part_{index:03d}.wav" for index in range(len(segments))]

        def _extract_one(item: tuple[VideoSegment, Path]) -> Path:
            seg, wav_path = item
            try:
                return extract_audio(seg.path, wav_path, ffmpeg, timeout)
            finally:
                seg.path.unlink(missing_ok=True)

        with ThreadPoolExecutor(max_workers=min(len(segments), max(1, parts))) as pool:
            list(pool.map(_extract_one, zip(segments, part_wavs)))

        with wave.open(str(output_path), "wb") as combined:
            combined.setnchannels(1)
            combined.setsampwidth(2)
            combined.setframerate(16000)
            for part_wav in part_wavs:
                try:
                    with wave.open(str(part_wav), "rb") as source:
                        if (
                            source.getnchannels(),
                            source.getsampwidth(),
                            source.getframerate(),
                            source.getcomptype(),
                        ) != (1, 2, 16000, "NONE"):
                            raise MediaProcessingError("Segment audio must be mono 16 kHz PCM WAV.")
                        while True:
                            frames = source.readframes(64 * 16000)
                            if not frames:
                                break
                            combined.writeframes(frames)
                finally:
                    part_wav.unlink(missing_ok=True)
    finally:
        shutil.rmtree(segments_dir, ignore_errors=True)

    if not output_path.is_file() or output_path.stat().st_size <= 44:
        raise MediaProcessingError("Audio extraction produced no readable audio.")
    return output_path
