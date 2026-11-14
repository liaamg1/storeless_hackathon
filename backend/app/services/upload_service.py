"""Small coordinator: existing services still own storage, extraction and comparison."""

from pathlib import Path
from typing import BinaryIO

from app.processors.pdf_processor import extract_pdf_pages
from app.repositories import upload_repository as repository
from app.repositories import visual_repository
from app.repositories.job_repository import percentage
from app.services import file_service, presentation_service, transcription_service
from app.services.duplicate_service import get_duplicate_summary
from app.services.storage_service import get_storage_savings

ALLOWED = {
    'pdf': {'pdf_text', 'slides', 'duplicates'},
    'pptx': {'slides', 'duplicates'},
    'video': {'transcribe', 'visuals', 'storage', 'duplicates'},
}
BASE = {'pdf': 'pdf_text', 'pptx': 'slides', 'video': 'transcribe'}
JOB_TYPES = {
    'slides': 'presentation_analysis',
    'transcribe': 'video_transcription',
    'visuals': 'video_visuals',
    'duplicates': 'duplicate_check',
}
OPERATION_ORDER = ('pdf_text', 'transcribe', 'slides', 'visuals', 'storage', 'duplicates')


class UploadedFileNotFoundError(ValueError):
    pass


def kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    types = {'.pdf': 'pdf', '.pptx': 'pptx', '.mp4': 'video'}
    if suffix not in types:
        raise file_service.UnsupportedFileError('Choose a PDF, PPTX presentation or MP4 recording.')
    return types[suffix]


def validate_selection(file_type: str, operations: list[str]) -> list[str]:
    selected = sorted(set(operations))
    if not selected or not set(selected) <= ALLOWED[file_type] or BASE[file_type] not in selected:
        raise file_service.InvalidUploadError(
            'Select the base text/slide processing operation and only actions supported by this file type.'
        )
    return selected


def coordinate(file_id: int, operations: list[str]) -> int:
    file = repository.snapshot(file_id)
    if file is None:
        raise UploadedFileNotFoundError('File not found.')
    visited = set()
    while file['original_removed_at'] is not None:
        if file_id in visited or not file['duplicate_of']:
            raise UploadedFileNotFoundError('Retained original not found.')
        visited.add(file_id)
        file_id = file['duplicate_of']
        file = repository.snapshot(file_id)
        if file is None:
            raise UploadedFileNotFoundError('Retained original not found.')
    file_type = kind(file['filename'])
    operations = validate_selection(file_type, operations)
    repository.merge_options(file_id, operations)
    if file_type == 'pdf' and not file['has_pages']:
        repository.queue(file_id, 'pdf_text')
    if 'transcribe' in operations:
        repository.queue(file_id, 'video_transcription')
    if 'slides' in operations:
        presentation_service.analyze_presentation(file_id)
    if 'visuals' in operations:
        # This queue only claims work after speech completes, including silent speech results.
        visual_repository.queue(file_id)
    if 'duplicates' in operations:
        repository.queue(file_id, 'duplicate_check')
    return file_id


def upload(source: BinaryIO, filename: str | None, operations: list[str]) -> dict:
    filename = (filename or '').replace('\\', '/').rsplit('/', 1)[-1]
    file_type = kind(filename)
    selected = validate_selection(file_type, operations)
    if file_type == 'pdf':
        file_id = file_service.upload_pdf(source, filename, processing_options=selected).id
    elif file_type == 'video':
        recording = transcription_service.upload_video(source, filename, processing_options=selected)
        file_id = recording.file_id
    else:
        file_id = presentation_service.upload_presentation(
            source, filename, processing_options=selected
        ).file_id
    file_id = coordinate(file_id, selected)
    return {**get_processing(file_id), 'reused': False}


def get_processing(file_id: int) -> dict:
    file = repository.snapshot(file_id)
    if file is None:
        raise UploadedFileNotFoundError('File not found.')
    file_type = kind(file['filename'])
    jobs = {job['job_type']: job for job in file['jobs']}
    operations = file['processing_options']
    if operations is None:
        operations = [op for op, job_type in JOB_TYPES.items() if job_type in jobs]
        if file_type == 'pdf' and file['has_pages']:
            operations.insert(0, 'pdf_text')
    operations = sorted(operations, key=OPERATION_ORDER.index)
    steps = []
    for op in operations:
        if op == 'pdf_text':
            job = jobs.get('pdf_text')
            step = (
                {
                    key: job[key]
                    for key in (
                        'status',
                        'current_step',
                        'error_message',
                        'progress_current',
                        'progress_total',
                        'progress_unit',
                    )
                }
                if job
                else {
                    'status': 'completed' if file['has_pages'] else 'queued',
                    'current_step': 'text_extracted' if file['has_pages'] else 'waiting_for_text',
                    'error_message': None,
                }
            )
        elif op == 'storage':
            prerequisites = [jobs.get('video_transcription')]
            if 'visuals' in operations:
                prerequisites.append(jobs.get('video_visuals'))
            if any(j and j['status'] == 'failed' for j in prerequisites):
                step = {
                    'status': 'failed',
                    'current_step': 'dependency_failed',
                    'error_message': 'Storage comparison requires completed processing.',
                }
            elif not all(j and j['status'] == 'completed' for j in prerequisites):
                step = {'status': 'queued', 'current_step': 'waiting_for_output', 'error_message': None}
            else:
                measured = get_storage_savings(file_id)
                step = {
                    'status': measured.status,
                    'current_step': 'storage_measured' if measured.status == 'completed' else measured.status,
                    'error_message': None if measured.status == 'completed' else measured.message,
                }
        else:
            job = jobs.get(JOB_TYPES[op])
            step = (
                {
                    key: job[key]
                    for key in (
                        'status',
                        'current_step',
                        'error_message',
                        'progress_current',
                        'progress_total',
                        'progress_unit',
                    )
                }
                if job
                else {'status': 'queued', 'current_step': 'waiting_for_processing', 'error_message': None}
            )
            if op == 'visuals' and jobs.get('video_transcription', {}).get('status') == 'failed':
                step = {
                    'status': 'failed',
                    'current_step': 'dependency_failed',
                    'error_message': 'Visual extraction is waiting for successful transcription. Retry this file.',
                }
        steps.append({'operation': op, **step, 'progress_percent': percentage(step)})
    statuses = [step['status'] for step in steps]
    status = (
        'failed'
        if any(s in ('failed', 'unavailable') for s in statuses)
        else 'processing' if 'processing' in statuses else 'queued' if 'queued' in statuses else 'completed'
    )
    incomplete = [step for step in steps if step['status'] != 'completed']
    priority = {'failed': 0, 'unavailable': 0, 'processing': 1, 'queued': 2}
    current = min(incomplete, key=lambda step: priority[step['status']]) if incomplete else None
    if not steps:
        status = 'queued'
    return {
        'file_id': file_id,
        'filename': file['filename'],
        'file_type': file_type,
        'size_bytes': file['size_bytes'],
        'operations': operations,
        'status': status,
        'current_step': current['current_step'] if current else 'completed' if steps else 'not_processed',
        'error_message': current['error_message'] if current else None,
        'steps': steps,
        'progress_percent': (
            100 if status == 'completed' else current.get('progress_percent') if current else None
        ),
        'progress_scope': 'current_step',
        'progress_current': current.get('progress_current') if current else None,
        'progress_total': current.get('progress_total') if current else None,
        'progress_unit': current.get('progress_unit') if current else None,
    }


def history() -> list[dict]:
    return [get_processing(file_id) for file_id in repository.history_ids()]
