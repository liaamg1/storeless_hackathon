import logging
from collections.abc import Callable
from typing import TypeVar
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, FileResponse, StreamingResponse
from app.services import visual_export, visual_service

from app.processors.audio_extractor import MediaProcessingError, MediaToolUnavailableError
from app.repositories import transcription_repository as repository
from app.schemas.transcription import ProcessingJob, VideoRecord, VideoTranscript, VideoUploadResult
from app.services.file_service import InvalidUploadError, UnsupportedFileError, UploadTooLargeError
from app.services.transcript_export import encode_transcript
from app.services.transcription_service import upload_video

router = APIRouter(tags=['transcription'])
logger = logging.getLogger(__name__)
T = TypeVar('T')


def database_response(action: Callable[[], T]) -> T:
    """Map shared read errors without leaking SQL, credentials, or transcript text."""
    try:
        return action()
    except repository.VideoNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except repository.TranscriptNotReadyError as exc:
        raise HTTPException(409, {
            'message': str(exc), 'status': exc.status, 'current_step': exc.current_step,
            'error_message': exc.error_message,
        }) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error('transcription_read_failed error_type=%s', type(exc).__name__)
        raise HTTPException(500, 'Recording data is unavailable. Please try again.') from exc


@router.post('/videos/upload', response_model=VideoUploadResult, status_code=202)
def upload_recording(file: UploadFile = File(...)) -> VideoUploadResult:
    try:
        return upload_video(file.file, file.filename)
    except UnsupportedFileError as exc:
        raise HTTPException(415, str(exc)) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except (InvalidUploadError, MediaProcessingError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except MediaToolUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        logger.error('video_upload_internal_failure error_type=%s', type(exc).__name__)
        raise HTTPException(500, 'Could not store or queue the recording. Please try again.') from exc
    finally:
        file.file.close()


@router.get('/videos', response_model=list[VideoRecord])
def list_recordings() -> list[VideoRecord]:
    return database_response(repository.list_videos)


@router.get('/videos/{file_id}', response_model=VideoRecord)
def get_recording(file_id: int) -> VideoRecord:
    def read() -> VideoRecord:
        video = repository.get_video(file_id)
        if video is None:
            raise repository.VideoNotFoundError('Recording not found.')
        return video
    return database_response(read)


@router.get('/jobs/{job_id}', response_model=ProcessingJob)
def get_processing_job(job_id: int) -> ProcessingJob:
    def read() -> ProcessingJob:
        job = repository.get_job(job_id)
        if job is None:
            raise HTTPException(404, 'Processing job not found.')
        return job
    return database_response(read)


@router.get('/videos/{file_id}/transcript', response_model=VideoTranscript)
def get_video_transcript(file_id: int) -> VideoTranscript:
    return database_response(lambda: repository.get_transcript(file_id))


@router.get('/videos/{file_id}/transcript/download')
def download_transcript(file_id: int) -> Response:
    transcript = database_response(lambda: repository.get_transcript(file_id))
    filename = transcript.filename.rsplit('.', 1)[0] + '.txt'
    return Response(encode_transcript(transcript), media_type='text/plain', headers={
        'Content-Disposition': (
            f'attachment; filename="transcript-{file_id}.txt"; '
            f"filename*=UTF-8''{quote(filename, safe='')}"
        ),
    })


@router.get('/videos/{file_id}/visual-transcript')
def visual_transcript(file_id: int) -> dict:
    return database_response(lambda: visual_service.get_visual_transcript(file_id))


@router.post('/videos/{file_id}/visual-transcript', status_code=202)
def start_visual_transcript(file_id: int) -> dict:
    return database_response(lambda: visual_service.enqueue(file_id))


@router.get('/videos/{file_id}/visuals/{frame_id}/image')
def visual_image(file_id: int, frame_id: int) -> FileResponse:
    path = database_response(lambda: visual_service.image_path(file_id, frame_id))
    return FileResponse(path, media_type='image/jpeg')


@router.get('/videos/{file_id}/visual-transcript/download')
def download_visual_transcript(file_id: int, timestamps: bool = False) -> StreamingResponse:
    filename, document = database_response(lambda: visual_export.prepare_download(file_id, timestamps))
    filename = filename.rsplit('.', 1)[0] + '-visual-transcript.html'
    return StreamingResponse(document, media_type='text/html', headers={
        'Content-Disposition': (
            f'attachment; filename="visual-transcript-{file_id}.html"; '
            f"filename*=UTF-8''{quote(filename, safe='')}"
        ),
        'X-Content-Type-Options': 'nosniff',
    })
