"""Compare the recorded upload size with measurable, generated output bytes."""
from pathlib import Path

from app.core.config import get_settings
from app.repositories import visual_repository
from app.repositories.file_repository import get_storage_source
from app.repositories.transcription_repository import get_transcript
from app.schemas.storage import StorageComponent, StorageSavings
from app.services.transcript_export import encode_transcript
from app.services.visual_export import prepare_download


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
    visual_state = visual_repository.state(file_id)
    if visual_state and visual_state['status'] != 'completed':
        result.status = 'failed' if visual_state['status'] == 'failed' else 'processing'
        result.message = 'Visual analysis is not complete. The speech transcript is available; total optimized storage is not yet measurable.'
        return result
    if visual_state:
        paths = {Path(frame['image_path']).resolve() for frame in visual_repository.frames(file_id)}
        root = (get_settings().upload_dir / 'visuals').resolve()
        if any(not path.is_relative_to(root) or not path.is_file() for path in paths):
            result.components[1].status = 'unavailable'
            result.message = 'An extracted image is missing. Total optimized storage cannot be measured.'
            return result
        if paths:
            result.components[1] = StorageComponent(
                kind='images', label='Extracted visuals (.jpg)', status='measured',
                size_bytes=sum(path.stat().st_size for path in paths), file_count=len(paths),
            )
    result.optimized_size_bytes = sum(
        component.size_bytes for component in result.components
        if component.status == 'measured' and component.size_bytes is not None
    )
    result.payload_size_bytes = result.optimized_size_bytes
    result.artifact_format = 'txt'
    result.download_url = f'/videos/{file_id}/transcript/download'
    if visual_state and paths:
        # Count the exact streamed download, including repeated images, UTF-8,
        # base64 and markup. Never assemble a complete export in RAM.
        _, chunks = prepare_download(file_id, timestamps=False)
        export_size = sum(len(chunk) for chunk in chunks)
        result.components[2] = StorageComponent(
            kind='other', label='HTML packaging adjustment', status='measured',
            size_bytes=export_size - result.payload_size_bytes,
        )
        result.optimized_size_bytes = export_size
        result.artifact_format = 'html'
        result.download_url = f'/videos/{file_id}/visual-transcript/download?timestamps=false'
    result.status = 'completed'
    result.message = (
        f'Potential savings based on the actual {result.artifact_format.upper()} download'
        + (' with timestamps off, including embedded images and encoding. ' if result.artifact_format == 'html' else '. ')
        +
        'The original upload is still retained.'
    )
    if result.original_size_bytes <= 0:
        result.status = 'unavailable'
        result.message = 'The original upload has no positive byte measurement, so a storage reduction cannot be calculated.'
    return result
