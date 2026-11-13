"""Compare the recorded upload size with measurable, generated output bytes."""
from app.repositories.file_repository import get_storage_source
from app.repositories.transcription_repository import get_transcript
from app.schemas.storage import StorageComponent, StorageSavings
from app.services.transcript_export import encode_transcript


class StorageFileNotFoundError(ValueError):
    pass


def get_storage_savings(file_id: int) -> StorageSavings:
    source = get_storage_source(file_id)
    if source is None:
        raise StorageFileNotFoundError('File not found.')
    components = [
        StorageComponent(kind='transcript', label='Transcript (.txt)', status='unavailable'),
        StorageComponent(kind='images', label='Slide images', status='not_generated'),
        StorageComponent(kind='other', label='Other generated files', status='not_generated'),
    ]
    result = StorageSavings(
        file_id=file_id, filename=source['filename'], original_size_bytes=source['size_bytes'],
        status='unavailable', components=components,
        message='No measurable optimized output file has been generated for this file.',
    )
    if source['file_type'] != 'video':
        result.components[1] = StorageComponent(kind='images', label='Slide previews (analysis only)', status='unavailable')
        result.message = (
            'Slide previews are analysis artifacts, not an optimized replacement. Byte savings are unavailable.'
            if source['file_type'] == 'pptx' else
            'PDF text is stored for search, but no optimized output file is generated. Storage comparison is unavailable.'
        )
        return result
    if source['job_status'] in ('queued', 'processing'):
        result.status = 'processing'
        result.message = (
            'Optimization is not complete yet. '
            'Storage savings will appear when the transcript is ready.'
        )
        return result
    if source['job_status'] == 'failed':
        result.status = 'failed'
        result.message = 'Processing failed. No completed optimized output is available to measure.'
        return result
    if source['job_status'] != 'completed':
        return result

    # Use the exact serializer used by the download endpoint, including UTF-8,
    # filename, separators and newlines. Never infer size from character counts.
    output = encode_transcript(get_transcript(file_id))
    result.components[0] = StorageComponent(
        kind='transcript', label='Transcript (.txt)', status='measured',
        size_bytes=len(output), file_count=1,
    )
    result.optimized_size_bytes = sum(
        component.size_bytes for component in result.components
        if component.status == 'measured' and component.size_bytes is not None
    )
    result.status = 'completed'
    result.message = (
        'Potential savings based on the exact downloadable text file. '
        'The original upload is still retained.'
    )
    if result.original_size_bytes <= 0:
        result.status = 'unavailable'
        result.message = 'The original upload has no positive byte measurement, so a storage reduction cannot be calculated.'
    return result
