"""Compare real download bytes and upload measurements using isolated PostgreSQL."""
import hashlib

import psycopg
import pytest

from app.processors.speech_recognizer import TranscriptSegment, TranscriptionResult
from app.repositories import transcription_repository, visual_repository
from app.services import storage_service


@pytest.fixture
def recording(database, tmp_path):
    def store(contents=b'original video bytes' * 1000, text='Hello world.', status='completed'):
        path = tmp_path / 'original.mp4'
        path.write_bytes(contents)
        result = transcription_repository.create_video_job(
            'Möte.mp4', path.stat().st_size, hashlib.sha256(contents).hexdigest(), path, 10000,
        )
        if status in ('processing', 'completed', 'failed'):
            job = transcription_repository.claim_next_job()
            if status == 'completed':
                transcription_repository.complete_transcription(job, TranscriptionResult(
                    'sv', [TranscriptSegment(0, 1000, text)] if text else [],
                ))
                # These fixtures represent fully processed recordings without visuals.
                visual_repository.complete(visual_repository.claim(), [])
            elif status == 'failed':
                transcription_repository.fail_job(job.job_id, 'Processing failed.')
        return result, path
    return store


def comparison(client, file_id):
    response = client.get(f'/files/{file_id}/storage-savings')
    assert response.status_code == 200, response.text
    return response.json()


def test_exact_utf8_output_and_metrics_preserve_original(client, recording):
    created, original = recording(text='Välkomna! 世界.\n\n')
    before = original.read_bytes()
    download = client.get(f'/videos/{created.file_id}/transcript/download')
    assert download.status_code == 200
    data = comparison(client, created.file_id)
    original_size = len(before)
    optimized_size = len(download.content)
    saved = original_size - optimized_size
    assert data['status'] == 'completed'
    assert data['filename'] == 'Möte.mp4'
    assert data['original_size_bytes'] == original_size
    assert data['optimized_size_bytes'] == optimized_size
    assert data['storage_saved_bytes'] == saved
    assert data['original_size_mb'] == original_size / 1_000_000
    assert data['optimized_size_mb'] == optimized_size / 1_000_000
    assert data['storage_saved_mb'] == saved / 1_000_000
    assert data['reduction_percent'] == pytest.approx(saved / original_size * 100)
    assert data['reduction_percent'] < 100
    assert optimized_size > len(download.text)  # Multibyte UTF-8 is counted as bytes.
    assert data['components'][0] == {
        'kind': 'transcript', 'label': 'Transcript (.txt)', 'status': 'measured',
        'size_bytes': optimized_size, 'file_count': 1,
    }
    assert data['optimized_size_bytes'] == sum(c['size_bytes'] for c in data['components'] if c['status'] == 'measured')
    assert all(c['size_bytes'] is None and c['status'] == 'not_generated' for c in data['components'][1:])
    assert 'Potential savings' in data['message']
    assert 'retained' in data['message']
    assert original.read_bytes() == before


@pytest.mark.parametrize('status,expected', [('queued', 'processing'), ('processing', 'processing'), ('failed', 'failed')])
def test_incomplete_outputs_have_no_invented_savings(client, recording, status, expected):
    created, _ = recording(status=status)
    data = comparison(client, created.file_id)
    assert data['status'] == expected
    for field in ('optimized_size_bytes', 'optimized_size_mb', 'storage_saved_bytes', 'storage_saved_mb', 'reduction_percent'):
        assert data[field] is None
    assert all(c['size_bytes'] is None for c in data['components'])
    assert data['message']


def test_pdf_without_generated_output_is_unavailable(client, database, pdf_bytes):
    source = pdf_bytes(('Actual extracted PDF content',))
    response = client.post('/files/upload', files={'file': ('notes.pdf', source, 'application/pdf')})
    assert response.status_code == 201
    data = comparison(client, response.json()['id'])
    assert data['status'] == 'unavailable'
    assert data['original_size_bytes'] == len(source)
    assert data['optimized_size_bytes'] is None
    assert data['reduction_percent'] is None
    assert 'no optimized output file' in data['message']


def test_larger_output_reports_negative_savings(client, recording):
    created, _ = recording(contents=b'x')
    data = comparison(client, created.file_id)
    assert data['status'] == 'completed'
    assert data['storage_saved_bytes'] == 1 - data['optimized_size_bytes'] < 0
    assert data['reduction_percent'] < 0


def test_zero_byte_original_does_not_divide_by_zero(client, recording):
    created, _ = recording(contents=b'')
    data = comparison(client, created.file_id)
    assert data['status'] == 'unavailable'
    assert data['original_size_bytes'] == 0
    assert data['reduction_percent'] is None


def test_empty_speech_measures_the_actual_generated_file(client, recording):
    created, _ = recording(text='')
    data = comparison(client, created.file_id)
    download = client.get(f'/videos/{created.file_id}/transcript/download')
    assert 'No speech was detected.' in download.text
    assert data['optimized_size_bytes'] == len(download.content) > 0


def test_other_files_are_not_mistaken_for_optimized_outputs(client, recording):
    created, original = recording()
    (original.parent / 'temporary-audio.wav').write_bytes(b'x' * 10000)
    data = comparison(client, created.file_id)
    assert data['optimized_size_bytes'] == len(client.get(f'/videos/{created.file_id}/transcript/download').content)
    assert data['components'][2]['status'] == 'not_generated'


def test_missing_file(client, database):
    assert client.get('/files/999999/storage-savings').status_code == 404


def test_missing_processing_job_is_unavailable(client, recording, database):
    created, _ = recording()
    with database() as connection:
        connection.execute('DELETE FROM processing_jobs WHERE file_id = %s', (created.file_id,))
    data = comparison(client, created.file_id)
    assert data['status'] == 'unavailable'
    assert data['optimized_size_bytes'] is None


def test_measurement_failure_is_private(client, monkeypatch, caplog):
    def fail(*args):
        raise psycopg.OperationalError('private credentials and transcript contents')
    monkeypatch.setattr(storage_service, 'get_storage_source', fail)
    response = client.get('/files/1/storage-savings')
    assert response.status_code == 500
    assert response.json()['detail'] == 'Storage comparison is unavailable. Please try again.'
    assert 'private credentials' not in response.text + caplog.text
