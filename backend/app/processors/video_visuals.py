"""Incremental sampled-frame extraction; all image buffers have a fixed size."""

from concurrent.futures import ThreadPoolExecutor
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Timer
from typing import BinaryIO

import numpy as np
import pymupdf

from app.processors.audio_extractor import MediaProcessingError, split_video_segments
from app.processors.slide_hash import hash_rendered_slide, perceptual_distance

WIDTH, HEIGHT = 1280, 720
FRAME_BYTES = WIDTH * HEIGHT * 3


class VisualExtractionError(ValueError):
    pass


@dataclass
class ExtractedFrame:
    start_ms: int
    end_ms: int
    image_path: Path
    image_hash: str
    size_bytes: int


def fingerprint(rgb: bytes) -> tuple[str, bool]:
    pixels = np.frombuffer(rgb, dtype=np.uint8).reshape(HEIGHT, WIDTH, 3)
    gray = pixels.mean(axis=2)
    small = gray[
        np.linspace(0, HEIGHT - 1, 32).astype(int)[:, None],
        np.linspace(0, WIDTH - 1, 32).astype(int),
    ]
    # A sparse slide has edges and contrast even when it never changes. These
    # conservative thresholds discard blank frames, not classify slide content.
    detail = float(np.abs(np.diff(gray, axis=1)).mean())
    meaningful = bool(gray.std() >= 8 and detail >= 0.08)
    return hash_rendered_slide(rgb, small.astype(np.uint8).tobytes(), '')[1], meaningful


def read_frame(stream: BinaryIO) -> bytes:
    """Pipe reads can be short; assemble exactly one frame, never the whole video."""
    chunks = bytearray()
    while len(chunks) < FRAME_BYTES:
        part = stream.read(FRAME_BYTES - len(chunks))
        if not part:
            break
        chunks.extend(part)
    if chunks and len(chunks) != FRAME_BYTES:
        raise VisualExtractionError('Video decoding produced an incomplete frame.')
    return bytes(chunks)


def extract_visuals(
    path: Path,
    output: Path,
    duration_ms: int,
    *,
    ffmpeg: str = 'ffmpeg',
    interval: float = 5,
    distance: int = 6,
    max_frames: int = 300,
    timeout: int = 3600,
    on_progress=None,
) -> list[ExtractedFrame]:
    if (
        not 1 <= interval <= 60
        or not 0 <= distance <= 64
        or max_frames < 1
        or timeout <= 0
        or duration_ms <= 0
    ):
        raise VisualExtractionError('Invalid visual extraction settings.')
    output.mkdir(parents=True, exist_ok=True)
    filters = (
        f'fps=1/{interval}:start_time=0:round=up,'
        f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,'
        f'pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:white'
    )
    args = [
        ffmpeg,
        '-nostdin',
        '-v',
        'error',
        '-threads',
        '1',
        '-protocol_whitelist',
        'file,pipe',
        '-i',
        str(path),
        '-an',
        '-vf',
        filters,
        '-threads',
        '1',
        '-pix_fmt',
        'rgb24',
        '-f',
        'rawvideo',
        'pipe:1',
    ]
    frames: list[ExtractedFrame] = []
    # stderr goes to a temporary file: corrupt media cannot grow a RAM error buffer.
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors)
        except FileNotFoundError as exc:
            raise VisualExtractionError('FFmpeg is required for visual analysis.') from exc
        timer = Timer(timeout, process.kill)
        timer.daemon = True
        started = time.monotonic()
        timer.start()
        previous = None
        current = None
        sample = 0
        try:
            while True:
                rgb = read_frame(process.stdout)
                if not rgb:
                    break
                timestamp = round(sample * interval * 1000)
                sample += 1
                if on_progress:
                    on_progress(sample, max(1, int(np.ceil(duration_ms / (interval * 1000)))))
                if timestamp >= duration_ms:
                    continue
                image_hash, meaningful = fingerprint(rgb)
                if not meaningful:
                    if current is not None:
                        current.end_ms = timestamp
                    current, previous = None, None
                    continue
                if previous is not None and perceptual_distance(previous, image_hash) <= distance:
                    continue
                if current is not None:
                    current.end_ms = timestamp
                current, previous = None, image_hash
                if len(frames) >= max_frames:
                    continue  # Uncovered speech is preserved without images.
                # Revisited visuals have separate intervals but share a compressed
                # image on disk (e.g. a presenter returns to the first diagram).
                reused = next(
                    (
                        frame
                        for frame in frames
                        if perceptual_distance(frame.image_hash, image_hash) <= distance
                    ),
                    None,
                )
                target = reused.image_path if reused else output / f'frame-{timestamp}.jpg'
                if reused is None:
                    pixmap = pymupdf.Pixmap(pymupdf.csRGB, WIDTH, HEIGHT, rgb, False)
                    target.write_bytes(pixmap.tobytes('jpeg', jpg_quality=80))
                current = ExtractedFrame(timestamp, duration_ms, target, image_hash, target.stat().st_size)
                frames.append(current)
            returncode = process.wait()
            if time.monotonic() - started >= timeout:
                raise VisualExtractionError('Visual analysis exceeded its time limit.')
            if returncode != 0:
                raise VisualExtractionError('The recording could not be decoded for visual analysis.')
            if sample == 0:
                raise VisualExtractionError('The recording contained no decodable video frames.')
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
    return [frame for frame in frames if frame.end_ms > frame.start_ms]


def extract_segmented_visuals(
    path: Path,
    output: Path,
    duration_ms: int,
    *,
    parts: int = 4,
    ffmpeg: str = 'ffmpeg',
    interval: float = 5,
    distance: int = 6,
    max_frames: int = 300,
    timeout: int = 3600,
    on_progress=None,
) -> list[ExtractedFrame]:
    """Split a large MP4 on keyframes via `-f segment -c copy` and decode visual frames in parallel."""
    if parts <= 1:
        return extract_visuals(
            path,
            output,
            duration_ms,
            ffmpeg=ffmpeg,
            interval=interval,
            distance=distance,
            max_frames=max_frames,
            timeout=timeout,
            on_progress=on_progress,
        )
    output.mkdir(parents=True, exist_ok=True)
    total_samples = max(1, int(np.ceil(duration_ms / (interval * 1000))))
    progress_lock = Lock()
    completed_samples = 0

    def _report_segment_progress(_done: int, _total: int) -> None:
        nonlocal completed_samples
        if not on_progress:
            return
        with progress_lock:
            completed_samples = min(total_samples, completed_samples + 1)
            on_progress(completed_samples, total_samples)

    with tempfile.TemporaryDirectory(prefix='restore-visual-seg-') as temp_root:
        temp_dir = Path(temp_root)
        try:
            segments = split_video_segments(
                path,
                temp_dir / 'mp4',
                duration_ms,
                parts=parts,
                ffmpeg=ffmpeg,
                timeout=timeout,
            )
        except MediaProcessingError as exc:
            raise VisualExtractionError('The recording could not be split for visual analysis.') from exc

        def _decode_segment(index_and_seg):
            idx, seg = index_and_seg
            seg_duration = max(1, seg.end_ms - seg.start_ms)
            seg_out = temp_dir / f'out_{idx:03d}'
            try:
                seg_frames = extract_visuals(
                    seg.path,
                    seg_out,
                    seg_duration,
                    ffmpeg=ffmpeg,
                    interval=interval,
                    distance=distance,
                    max_frames=max_frames,
                    timeout=timeout,
                    on_progress=_report_segment_progress if on_progress else None,
                )
                return idx, seg, seg_frames
            finally:
                seg.path.unlink(missing_ok=True)

        with ThreadPoolExecutor(max_workers=min(len(segments), max(1, parts))) as pool:
            decoded = list(pool.map(_decode_segment, enumerate(segments)))

        merged: list[ExtractedFrame] = []
        for _idx, seg, seg_frames in sorted(decoded, key=lambda item: item[0]):
            for frame in seg_frames:
                abs_start = seg.start_ms + frame.start_ms
                abs_end = min(duration_ms, seg.start_ms + frame.end_ms)
                if abs_end <= abs_start:
                    continue
                if (
                    merged
                    and merged[-1].end_ms >= seg.start_ms
                    and perceptual_distance(merged[-1].image_hash, frame.image_hash) <= distance
                ):
                    merged[-1].end_ms = max(merged[-1].end_ms, abs_end)
                    continue
                if len(merged) >= max_frames:
                    continue
                reused = next(
                    (
                        existing
                        for existing in merged
                        if perceptual_distance(existing.image_hash, frame.image_hash) <= distance
                    ),
                    None,
                )
                if reused is not None:
                    target = reused.image_path
                else:
                    target = output / f'frame-{abs_start}.jpg'
                    if not target.exists():
                        shutil.move(str(frame.image_path), str(target))
                merged.append(
                    ExtractedFrame(
                        abs_start,
                        abs_end,
                        target,
                        frame.image_hash,
                        target.stat().st_size,
                    )
                )

    return merged
