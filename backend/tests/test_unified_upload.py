"""Central coordination uses existing pipelines and disposable PostgreSQL schemas."""

import io
import json
from pathlib import Path

import pytest

from app.processors.audio_extractor import VideoMetadata
from app.processors.speech_recognizer import TranscriptSegment, TranscriptionResult
from app.repositories import (
    transcription_repository as speech,
    visual_repository as visuals,
    presentation_repository as slides,
)
from app.services import transcription_service, upload_service
from app.services.file_service import CHUNK_SIZE
from app.repositories import job_repository
from app.services import document_jobs


def upload(client, name, contents, operations):
    return client.post(
        '/uploads',
        files={'file': (name, contents, 'application/octet-stream')},
        data={'operations': json.dumps(operations)},
    )


def test_pdf_text_only_does_not_start_slide_analysis(client, database, pdf_bytes, uploads):
    response = upload(client, 'notes.pdf', pdf_bytes(('Searchable unique topic',)), ['pdf_text'])
    assert response.status_code == 202, response.text
    data = response.json()
    assert data['file_type'] == 'pdf' and data['status'] == 'queued' and not data['reused']
    document_jobs.process_document_job(job_repository.claim('document'))
    assert data['operations'] == ['pdf_text']
    assert slides.claim_presentation_job() is None
    assert client.get('/uploads').json()[0]['file_id'] == data['file_id']
    assert client.get(f"/uploads/{data['file_id']}").json()['status'] == 'completed'
    assert (
        client.get(f"/files/{data['file_id']}/pages").json()['pages'][0]['text'].strip()
        == 'Searchable unique topic'
    )
    assert len(list(uploads.glob('*.pdf'))) == 1


def test_same_content_is_reused_and_new_operations_added_once(client, database, pdf_bytes, uploads):
    content = pdf_bytes(('Duplicate content',))
    first = upload(client, 'first.pdf', content, ['pdf_text']).json()
    again = upload(client, 'renamed.pdf', content, ['pdf_text', 'slides', 'duplicates'])
    assert again.status_code == 202, again.text
    data = again.json()
    assert data['reused'] and data['file_id'] == first['file_id'] and data['filename'] == 'first.pdf'
    assert len(list(uploads.glob('*.pdf'))) == 1
    assert data['status'] == 'queued'
    assert next(step for step in data['steps'] if step['operation'] == 'duplicates')['status'] == 'queued'
    document_jobs.process_document_job(job_repository.claim('document'))
    job = slides.claim_presentation_job()
    assert job and job.file_id == data['file_id'] and slides.claim_presentation_job() is None
    original = Path(slides.get_source(job.file_id)['storage_path']).read_bytes()
    response = client.post(f"/uploads/{job.file_id}/process", json={'operations': ['pdf_text', 'slides']})
    assert response.status_code == 202 and slides.claim_presentation_job() is None
    assert Path(slides.get_source(job.file_id)['storage_path']).read_bytes() == original


@pytest.fixture
def fake_video(monkeypatch):
    monkeypatch.setattr(transcription_service, 'validate_video', lambda *args: VideoMetadata(10000))


def finish_speech():
    job = speech.claim_next_job()
    speech.complete_transcription(
        job, TranscriptionResult('en', [TranscriptSegment(0, 1000, 'Persisted searchable speech.')])
    )
    return job


def test_video_without_visual_selection_remains_transcript_only(client, database, fake_video):
    data = upload(client, 'speech.mp4', b'video', ['transcribe', 'storage']).json()
    job = finish_speech()
    assert visuals.state(job.file_id) is None and visuals.claim() is None
    result = client.get(f"/uploads/{data['file_id']}").json()
    assert result['status'] == 'completed'
    assert {step['operation']: step['status'] for step in result['steps']} == {
        'storage': 'completed',
        'transcribe': 'completed',
    }
    assert (
        client.get(f'/videos/{job.file_id}/transcript').json()['segments'][0]['text']
        == 'Persisted searchable speech.'
    )


def test_visuals_wait_for_speech_and_failure_is_reported_truthfully(client, database, fake_video):
    data = upload(client, 'visual.mp4', b'video2', ['transcribe', 'visuals', 'storage']).json()
    assert data['status'] == 'queued' and visuals.claim() is None
    job = finish_speech()
    midway = client.get(f'/uploads/{job.file_id}').json()
    assert midway['status'] == 'queued'
    assert next(step for step in midway['steps'] if step['operation'] == 'storage')['status'] == 'queued'
    visual = visuals.claim()
    speech.fail_job(visual['job_id'], 'Visual decoding failed.')
    result = client.get(f'/uploads/{job.file_id}').json()
    assert result['status'] == 'failed'
    assert (
        next(step for step in result['steps'] if step['operation'] == 'transcribe')['status'] == 'completed'
    )
    assert (
        next(step for step in result['steps'] if step['operation'] == 'visuals')['error_message']
        == 'Visual decoding failed.'
    )
    retry = client.post(
        f'/uploads/{job.file_id}/process', json={'operations': ['transcribe', 'visuals', 'storage']}
    )
    assert retry.status_code == 202 and speech.claim_next_job() is None
    assert visuals.claim() is not None


def test_speech_failure_blocks_dependent_steps_and_retry_reuses_original(
    client, database, fake_video, uploads
):
    data = upload(client, 'failed.mp4', b'video3', ['transcribe', 'visuals', 'storage']).json()
    job = speech.claim_next_job()
    speech.fail_job(job.job_id, 'Recognition failed.')
    result = client.get(f'/uploads/{job.file_id}').json()
    assert result['status'] == 'failed'
    assert all(step['status'] == 'failed' for step in result['steps'])
    retry = client.post(f'/uploads/{job.file_id}/process', json={'operations': ['transcribe', 'visuals']})
    assert retry.status_code == 202 and len(list(uploads.glob('*.mp4'))) == 1
    assert speech.claim_next_job().file_id == data['file_id']


@pytest.mark.parametrize(
    'name,operations',
    [
        ('bad.exe', ['pdf_text']),
        ('notes.pdf', ['visuals']),
        ('notes.pdf', ['slides']),
        ('meeting.mp4', ['visuals']),
        ('deck.pptx', ['slides', 'storage']),
    ],
)
def test_invalid_type_or_dependencies_never_upload(client, database, uploads, name, operations):
    result = upload(client, name, b'bytes', operations)
    assert result.status_code in (400, 415)
    assert not uploads.exists()


def test_current_limits_enforced_and_reported(client, database, monkeypatch):
    monkeypatch.setenv('MAX_UPLOAD_BYTES', '20')
    monkeypatch.setenv('MAX_VIDEO_UPLOAD_BYTES', '40')
    assert client.get('/uploads/limits').json() == {'pdf': 20, 'pptx': 20, 'video': 40}
    assert upload(client, 'large.pdf', b'x' * 21, ['pdf_text']).status_code == 413
    assert upload(client, 'large.mp4', b'x' * 41, ['transcribe']).status_code == 413


def test_unsupported_payloads_missing_records_and_original_privacy(client, database):
    assert (
        client.post(
            '/uploads', files={'file': ('a.pdf', b'pdf')}, data={'operations': 'not json'}
        ).status_code
        == 400
    )
    assert client.get('/uploads/999999').status_code == 404
    assert client.post('/uploads/999999/process', json={'operations': ['pdf_text']}).status_code == 404
    assert upload(client, 'empty.pdf', b'', ['pdf_text']).status_code == 400


def test_reuse_dedicated_upload_without_mutating_text_or_duplicate_jobs(client, database, pdf_bytes):
    content = pdf_bytes(('Existing extraction preserved',))
    first = client.post('/files/upload', files={'file': ('legacy.pdf', content, 'application/pdf')}).json()
    before = client.get(f"/files/{first['id']}/pages").json()
    reused = upload(client, 'new.pdf', content, ['pdf_text']).json()
    assert reused['reused'] and reused['file_id'] == first['id']
    assert client.get(f"/files/{first['id']}/pages").json() == before
    assert reused['operations'] == ['pdf_text', 'slides']  # Prior authorized analysis is retained.


def test_hash_identification_reads_fixed_chunks():
    class BoundedStream(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= CHUNK_SIZE
            return super().read(size)

    from app.services.file_service import save_uploaded_file

    stream = BoundedStream(b'x' * (CHUNK_SIZE * 3 + 7))
    size, digest = save_uploaded_file(stream, None, CHUNK_SIZE * 4)
    assert size == CHUNK_SIZE * 3 + 7 and len(digest) == 64


def test_failed_duplicate_scan_is_not_reported_as_completed(client, database, pdf_bytes, monkeypatch):
    def fail():
        raise RuntimeError('private contents')

    monkeypatch.setattr(document_jobs, 'get_duplicate_summary', fail)
    result = upload(client, 'dup.pdf', pdf_bytes(('text',)), ['pdf_text', 'duplicates'])
    assert result.status_code == 202
    data = result.json()
    assert data['status'] == 'queued'
    document_jobs.process_document_job(job_repository.claim('document'))
    document_jobs.process_document_job(job_repository.claim('document'))
    result = client.get(f"/uploads/{data['file_id']}")
    data = result.json()
    assert data['status'] == 'failed' and 'private contents' not in result.text
    assert next(s for s in data['steps'] if s['operation'] == 'pdf_text')['status'] == 'completed'


def test_pptx_uses_existing_slide_pipeline_and_real_completion(client, database):
    from presentation_fixtures import make_pptx
    from app.services.presentation_service import process_presentation_job

    result = upload(
        client, 'training.pptx', make_pptx(('Unified upload searchable training',)), ['slides', 'duplicates']
    )
    assert result.status_code == 202, result.text
    data = result.json()
    assert data['file_type'] == 'pptx' and data['status'] == 'queued'
    job = slides.claim_presentation_job()
    process_presentation_job(job)
    document_jobs.process_document_job(job_repository.claim('document'))
    current = client.get(f'/uploads/{job.file_id}').json()
    assert current['status'] == 'completed', current
    assert client.get(f'/presentations/{job.file_id}').json()['slide_count'] == 1
    assert client.get('/search', params={'q': 'searchable'}).json()['results'][0]['file_id'] == job.file_id
