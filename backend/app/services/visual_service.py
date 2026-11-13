"""Independent visual analysis and deterministic timestamp synchronization."""
import logging
import os
import shutil
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings, get_transcription_settings
from app.processors.video_visuals import VisualExtractionError, extract_visuals
from app.repositories import visual_repository as repository
from app.repositories.transcription_repository import (
    TranscriptNotReadyError, VideoNotFoundError, fail_job, get_job, get_transcript, get_video,
)

logger = logging.getLogger(__name__)


def synchronize(frames: list[dict], segments: list[dict]) -> list[dict]:
    """Assign each segment once by greatest positive overlap; ties go earlier.

    Uncovered speech stays in chronological sections. Visuals displayed during
    silence remain visible. Paths never leave the backend.
    """
    sections = [
        {'visual': {k: v for k, v in frame.items() if k != 'image_path'}, 'segments': []}
        for frame in sorted(frames, key=lambda f: f['start_ms'])
    ]
    visual_sections = list(sections)
    for segment in sorted(segments, key=lambda s: (s['start_ms'], s['id'])):
        best = None
        overlap = 0
        for section in visual_sections:
            frame = section['visual']
            amount = max(0, min(segment['end_ms'], frame['end_ms']) - max(segment['start_ms'], frame['start_ms']))
            if amount > overlap:
                best, overlap = section, amount
        if best is None:
            sections.append({'visual': None, 'segments': [segment]})
        else:
            best['segments'].append(segment)
    sections.sort(key=lambda s: s['visual']['start_ms'] if s['visual'] else s['segments'][0]['start_ms'])
    return sections


def enqueue(file_id: int) -> dict:
    video = get_video(file_id)
    if video is None:
        raise VideoNotFoundError('Recording not found.')
    if video.status != 'completed':
        job = get_job(video.job_id)
        raise TranscriptNotReadyError(video.status, job.current_step, job.error_message)
    repository.queue(file_id)
    return {'status': (repository.state(file_id) or {}).get('status', 'queued')}


def get_visual_transcript(file_id: int) -> dict:
    video = get_video(file_id)
    if video is None:
        raise VideoNotFoundError('Recording not found.')
    state = repository.state(file_id) or {
        'status': 'not_processed', 'current_step': None, 'error_message': None,
    }
    transcript = get_transcript(file_id) if video.status == 'completed' else None
    frames = repository.frames(file_id) if state['status'] == 'completed' else []
    image_references = {}
    for frame in frames:
        # Intervals can revisit a saved image. Expose its first ID, never its path,
        # so the UI can distinguish existing disk reuse from suggested cleanup.
        frame['image_reference_id'] = image_references.setdefault(frame['image_path'], frame['id'])
    return {
        'file_id': file_id, 'filename': video.filename, **state,
        'speech_status': video.status,
        'sections': synchronize(frames, [s.model_dump() for s in transcript.segments]) if transcript else [],
    }


def resolve_image_path(stored_path: str) -> Path:
    """Validate generated-image paths for both previews and document exports."""
    root = (get_settings().upload_dir / 'visuals').resolve()
    path = Path(stored_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise VideoNotFoundError('Visual image not found.')
    return path


def image_path(file_id: int, frame_id: int) -> Path:
    frame = next((f for f in repository.frames(file_id) if f['id'] == frame_id), None)
    if frame is None:
        raise VideoNotFoundError('Visual image not found.')
    if (repository.state(file_id) or {}).get('status') != 'completed':
        raise VideoNotFoundError('Visual image not available.')
    return resolve_image_path(frame['image_path'])


def process_visual_job(job: dict) -> None:
    output = get_settings().upload_dir / 'visuals' / str(job['file_id']) / uuid4().hex
    try:
        # A killed worker cannot run its finally block. A retry removes only
        # uncommitted image attempts for this file, never original uploads.
        referenced = {Path(frame['image_path']).resolve().parent for frame in repository.frames(job['file_id'])}
        if output.parent.is_dir():
            for attempt in output.parent.iterdir():
                if (len(attempt.name) == 32 and all(c in '0123456789abcdef' for c in attempt.name)
                        and attempt.is_dir() and not attempt.is_symlink() and attempt.resolve() not in referenced):
                    shutil.rmtree(attempt)
        settings = get_transcription_settings()
        frames = extract_visuals(
            Path(job['storage_path']), output, job['duration_ms'], ffmpeg=settings.ffmpeg,
            interval=float(os.getenv('VISUAL_SAMPLE_INTERVAL_SECONDS', '5')),
            distance=int(os.getenv('VISUAL_HASH_DISTANCE', '6')),
            max_frames=int(os.getenv('VISUAL_MAX_FRAMES', '300')), timeout=settings.media_timeout,
        )
        repository.complete(job, frames)
        logger.info('visual_analysis_completed job_id=%s frame_count=%s', job['job_id'], len(frames))
    except Exception as exc:
        if output.is_dir():
            shutil.rmtree(output)
        logger.error('visual_analysis_failed job_id=%s error_type=%s', job['job_id'], type(exc).__name__)
        message = str(exc) if isinstance(exc, VisualExtractionError) else (
            'Visual analysis failed. The speech transcript and original recording are preserved.'
        )
        fail_job(job['job_id'], message)
