"""Incremental sampled-frame extraction; all image buffers have a fixed size."""
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Timer
from typing import BinaryIO

import numpy as np
import pymupdf

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
    path: Path, output: Path, duration_ms: int, *, ffmpeg: str = 'ffmpeg',
    interval: float = 5, distance: int = 6, max_frames: int = 300, timeout: int = 3600,
) -> list[ExtractedFrame]:
    if (not 1 <= interval <= 60 or not 0 <= distance <= 64 or
            max_frames < 1 or timeout <= 0 or duration_ms <= 0):
        raise VisualExtractionError('Invalid visual extraction settings.')
    output.mkdir(parents=True, exist_ok=True)
    filters = (
        f'fps=1/{interval}:start_time=0:round=up,'
        f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,'
        f'pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:white'
    )
    args = [
        ffmpeg, '-nostdin', '-v', 'error', '-threads', '1', '-protocol_whitelist', 'file,pipe',
        '-i', str(path), '-an', '-vf', filters,
        '-threads', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1',
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
                reused = next((
                    frame for frame in frames
                    if perceptual_distance(frame.image_hash, image_hash) <= distance
                ), None)
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
