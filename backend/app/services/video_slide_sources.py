"""Review-only video-to-presentation links using bounded cached image hashes."""

from functools import lru_cache
import os
from pathlib import Path

import numpy as np
import pymupdf

from app.core.config import get_settings
from app.processors.slide_hash import hash_rendered_slide, perceptual_distance
from app.repositories import presentation_repository, visual_repository
from app.repositories.transcription_repository import VideoNotFoundError, get_video
from app.services.visual_service import resolve_image_path


@lru_cache(maxsize=1024)
def normalized_hash(path: str, modified_ns: int, size: int) -> str | None:
    """Trim near-white page padding, then use the same 32x32 hash for both media.

    Only hash strings are cached; decoded images are discarded after each call.
    Cropping makes 16:9 video frames comparable with letterboxed slide renders.
    Camera overlays, animations and screen chrome can still prevent a match.
    """
    pixmap = pymupdf.Pixmap(path)
    if pixmap.alpha:
        pixmap = pymupdf.Pixmap(pixmap, 0)
    if pixmap.colorspace.n != 3:
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
    if pixmap.width * pixmap.height > 2_000_000:
        return None
    pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)
    foreground = pixels.min(axis=2) < 245
    ys, xs = np.where(foreground)
    if not len(xs) or pixels.std() < 3:
        return None
    crop = pixels[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    # Both sides use an identical sampling recipe; existing slide hashes remain unchanged.
    gray = crop.mean(axis=2)
    if gray.std() < 3:
        return None
    sample = gray[
        np.linspace(0, crop.shape[0] - 1, 32).astype(int)[:, None],
        np.linspace(0, crop.shape[1] - 1, 32).astype(int),
    ]
    return hash_rendered_slide(b'', sample.astype(np.uint8).tobytes(), '')[1]


def image_hash(path: Path) -> str | None:
    stat = path.stat()
    return normalized_hash(str(path), stat.st_mtime_ns, stat.st_size)


def find_sources(file_id: int) -> dict:
    if get_video(file_id) is None:
        raise VideoNotFoundError('Recording not found.')
    state = visual_repository.state(file_id) or {'status': 'not_processed'}
    threshold = float(os.getenv('VIDEO_SLIDE_MATCH_THRESHOLD', '90'))
    if not 0 <= threshold <= 100:
        raise ValueError('VIDEO_SLIDE_MATCH_THRESHOLD must be between 0 and 100.')
    result = {
        'file_id': file_id,
        'status': state['status'],
        'threshold': threshold,
        'slides_compared': 0,
        'skipped_images': 0,
        'frames': [],
    }
    if state['status'] != 'completed':
        return result
    root = (get_settings().upload_dir / 'slides').resolve()
    candidates = []
    for slide in presentation_repository.get_analyzed_slides():
        try:
            path = Path(slide['image_path']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError('Unavailable slide image')
            digest = image_hash(path)
            if digest is not None:
                candidates.append((slide, digest))
        except (OSError, ValueError, RuntimeError, TypeError, VideoNotFoundError):
            result['skipped_images'] += 1
    result['slides_compared'] = len(candidates)
    # References remain suggestions. Never replace/delete a frame on perceptual similarity.
    for frame in visual_repository.frames(file_id):
        matches = []
        try:
            digest = image_hash(resolve_image_path(frame['image_path']))
            if digest is not None:
                for slide, other in candidates:
                    score = (1 - perceptual_distance(digest, other) / 64) * 100
                    if score >= threshold:
                        matches.append(
                            {
                                'slide_id': slide['id'],
                                'file_id': slide['file_id'],
                                'filename': slide['filename'],
                                'slide_number': slide['slide_number'],
                                'similarity_percent': round(score, 2),
                            }
                        )
        except (OSError, ValueError, RuntimeError, TypeError, VideoNotFoundError):
            result['skipped_images'] += 1
        matches.sort(key=lambda item: (-item['similarity_percent'], item['file_id'], item['slide_number']))
        result['frames'].append(
            {'frame_id': frame['id'], 'matches': matches[:3], 'candidate_count': len(matches)}
        )
    return result
