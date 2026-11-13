"""Jobs and transcripts use the same isolated PostgreSQL fixture as other features."""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest

from app.processors.audio_extractor import MediaProcessingError, VideoMetadata, extract_audio, validate_video
from app.processors.speech_recognizer import SpeechRecognitionError, TranscriptSegment, TranscriptionResult
from app.repositories import transcription_repository as repository
from app.services import transcription_service


@pytest.fixture
def fake_video_tools(monkeypatch):
    monkeypatch.setattr(transcription_service, 'validate_video', lambda *args: VideoMetadata(10000))
    audio_paths = []
    def extract(source, target, *args):
        target.write_bytes(b'audio')
        audio_paths.append(target)
        return target
    monkeypatch.setattr(transcription_service, 'extract_audio', extract)
    monkeypatch.setattr(transcription_service, 'transcribe_audio', lambda *args, **kwargs: TranscriptionResult('en', [
        TranscriptSegment(2500, 4000, 'Second segment'), TranscriptSegment(500, 1500, 'First segment'),
    ]))
    return audio_paths


def upload(client, contents=b'video test bytes', filename='meeting.mp4'):
    return client.post('/videos/upload', files={'file': (filename, contents, 'video/mp4')})


def test_video_upload_creates_job_and_hash(client, database, fake_video_tools, uploads):
    contents = b'actual bytes for hashing'
    response = upload(client, contents, '../../meeting.mp4')
    assert response.status_code == 202
    created = response.json()
    assert created['filename'] == 'meeting.mp4'
    assert created['status'] == 'queued'
    with database() as connection:
        file = connection.execute('SELECT * FROM files WHERE id = %s', (created['file_id'],)).fetchone()
        assert file['sha256'] == hashlib.sha256(contents).hexdigest()
        assert file['size_bytes'] == len(contents)
        assert file['file_type'] == 'video'
        assert file['duration_ms'] == 10000
        assert Path(file['storage_path']).parent == uploads
        assert Path(file['storage_path']).read_bytes() == contents
        assert connection.execute('SELECT count(*) AS count FROM transcript_segments').fetchone()['count'] == 0
    job = client.get(f"/jobs/{created['job_id']}").json()
    assert job['status'] == 'queued'
    assert job['current_step'] == 'queued'
    assert job['started_at'] is None
    assert client.get('/videos').json()[0]['file_id'] == created['file_id']
    assert client.get(f"/videos/{created['file_id']}").status_code == 200
    assert client.get(f"/videos/{created['file_id']}/transcript").status_code == 409
    assert client.get(f"/videos/{created['file_id']}/transcript/download").status_code == 409


def test_pipeline_saves_ordered_transcript_and_download(client, database, fake_video_tools, monkeypatch):
    created = upload(client).json()
    job = repository.claim_next_job()
    assert job.job_id == created['job_id']
    assert repository.claim_next_job() is None
    stages = [repository.get_job(job.job_id).current_step]
    original_update = repository.update_job_step
    def update(job_id, step):
        original_update(job_id, step)
        stages.append(repository.get_job(job_id).current_step)
    monkeypatch.setattr(repository, 'update_job_step', update)
    transcription_service.process_video_job(job)
    assert stages == ['validating_video', 'extracting_audio', 'transcribing_audio', 'saving_transcript']
    assert not fake_video_tools[0].exists()
    assert job.storage_path.exists()
    status = client.get(f'/jobs/{job.job_id}').json()
    assert status['status'] == 'completed'
    assert status['current_step'] == 'completed'
    assert status['started_at'] and status['completed_at']
    transcript = client.get(f'/videos/{job.file_id}/transcript').json()
    assert transcript['language'] == 'en'
    assert [segment['start_ms'] for segment in transcript['segments']] == [500, 2500]
    assert transcript['segments'][0]['text'] == 'First segment'
    download = client.get(f'/videos/{job.file_id}/transcript/download')
    assert download.status_code == 200
    assert download.headers['content-type'].startswith('text/plain')
    assert 'filename="transcript-' in download.headers['content-disposition']
    assert "filename*=UTF-8''meeting.txt" in download.headers['content-disposition']
    assert download.text == 'meeting.mp4\n\nFirst segment Second segment\n'
    assert transcript['paragraphs'] == [[segment['id'] for segment in transcript['segments']]]
    assert repository.claim_next_job() is None
    # Reopening persisted results must not create or rerun a job.
    assert client.get(f'/videos/{job.file_id}/transcript').json() == transcript


@pytest.mark.parametrize('filename,contents,limit,status', [
    ('notes.txt', b'video', 200000000, 415), ('empty.mp4', b'', 200000000, 400),
    ('large.mp4', b'x' * 100, 50, 413),
])
def test_invalid_uploads(client, database, uploads, monkeypatch, filename, contents, limit, status):
    monkeypatch.setenv('MAX_VIDEO_UPLOAD_BYTES', str(limit))
    assert upload(client, contents, filename).status_code == status
    assert not list(uploads.glob('*.mp4'))
    with database() as connection:
        assert connection.execute('SELECT count(*) AS count FROM processing_jobs').fetchone()['count'] == 0


def test_corrupted_upload_is_cleaned_up(client, database, uploads, monkeypatch):
    def invalid(*args):
        raise MediaProcessingError('Upload a valid MP4 containing a video stream.')
    monkeypatch.setattr(transcription_service, 'validate_video', invalid)
    assert upload(client).status_code == 400
    assert not list(uploads.glob('*.mp4'))


def test_missing_ffprobe(client, uploads, monkeypatch):
    monkeypatch.setenv('FFPROBE_BINARY', '/definitely/missing/ffprobe')
    assert upload(client).status_code == 503
    assert not list(uploads.glob('*.mp4'))


def test_video_metadata_and_job_insert_roll_back_together(client, database, fake_video_tools, uploads):
    with database() as connection:
        before = connection.execute('SELECT count(*) AS count FROM files').fetchone()['count']
        connection.execute("ALTER TABLE processing_jobs ADD CONSTRAINT reject_test_job CHECK (job_type <> 'video_transcription')")
    assert upload(client).status_code == 500
    assert not list(uploads.glob('*.mp4'))
    with database() as connection:
        assert connection.execute('SELECT count(*) AS count FROM files').fetchone()['count'] == before


def test_transcript_insert_failure_rolls_back_and_marks_failed(client, database, fake_video_tools, monkeypatch):
    upload(client)
    job = repository.claim_next_job()
    monkeypatch.setattr(transcription_service, 'transcribe_audio', lambda *args, **kwargs: TranscriptionResult('en', [
        TranscriptSegment(0, 100, 'First'), TranscriptSegment(200, 100, 'Invalid end time'),
    ]))
    transcription_service.process_video_job(job)
    assert repository.get_job(job.job_id).status == 'failed'
    assert job.storage_path.exists()
    assert not fake_video_tools[0].exists()
    with database() as connection:
        assert connection.execute('SELECT count(*) AS count FROM transcript_segments').fetchone()['count'] == 0
        assert connection.execute('SELECT transcript_language FROM files WHERE id = %s', (job.file_id,)).fetchone()['transcript_language'] is None
    response = client.get(f'/videos/{job.file_id}/transcript')
    assert response.status_code == 409
    assert response.json()['detail']['status'] == 'failed'


@pytest.mark.parametrize('failure', [MediaProcessingError('Audio extraction failed.'), SpeechRecognitionError('Could not load the speech model.')])
def test_processing_failures_preserve_original_and_clean_audio(client, database, fake_video_tools, monkeypatch, failure):
    upload(client)
    job = repository.claim_next_job()
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(transcription_service, 'transcribe_audio', fail)
    transcription_service.process_video_job(job)
    saved_job = repository.get_job(job.job_id)
    assert saved_job.status == 'failed'
    assert saved_job.error_message == str(failure)
    assert job.storage_path.exists()
    assert not fake_video_tools[0].exists()


def test_no_speech_is_a_completed_empty_transcript(client, database, fake_video_tools, monkeypatch):
    upload(client)
    job = repository.claim_next_job()
    monkeypatch.setattr(transcription_service, 'transcribe_audio', lambda *args, **kwargs: TranscriptionResult('en', []))
    transcription_service.process_video_job(job)
    transcript = client.get(f'/videos/{job.file_id}/transcript').json()
    assert transcript['status'] == 'completed'
    assert transcript['segments'] == []
    assert 'No speech was detected.' in client.get(f'/videos/{job.file_id}/transcript/download').text


def test_interrupted_job_recovery_keeps_queued_jobs(client, database, fake_video_tools):
    upload(client)
    interrupted = repository.claim_next_job()
    waiting = upload(client).json()
    assert repository.fail_interrupted_jobs() == 1
    assert repository.get_job(interrupted.job_id).status == 'failed'
    assert 'interrupted' in repository.get_job(interrupted.job_id).error_message
    assert interrupted.storage_path.exists()
    assert repository.get_job(waiting['job_id']).status == 'queued'
    assert repository.fail_interrupted_jobs() == 0


@pytest.mark.parametrize('path', ['/jobs/99999', '/videos/99999', '/videos/99999/transcript', '/videos/99999/transcript/download'])
def test_missing_video_and_jobs(client, database, path):
    assert client.get(path).status_code == 404


def test_database_errors_are_private(client, monkeypatch, caplog):
    def fail():
        raise psycopg.OperationalError('postgresql://secret credentials SQL transcript text')
    monkeypatch.setattr(repository, 'get_connection', fail)
    for path in ['/videos', '/jobs/1', '/videos/1/transcript']:
        response = client.get(path)
        assert response.status_code == 500
        assert 'secret credentials' not in response.text
    assert 'secret credentials' not in caplog.text


@pytest.fixture
def media_tools(monkeypatch):
    ffmpeg = shutil.which(os.getenv('FFMPEG_BINARY', 'ffmpeg'))
    ffprobe = shutil.which(os.getenv('FFPROBE_BINARY', 'ffprobe'))
    if not ffmpeg or not ffprobe:
        pytest.skip('Install FFmpeg/FFprobe or set FFMPEG_BINARY/FFPROBE_BINARY for real media tests')
    monkeypatch.setenv('FFMPEG_BINARY', ffmpeg)
    monkeypatch.setenv('FFPROBE_BINARY', ffprobe)
    return ffmpeg, ffprobe


def test_real_ffmpeg_mp4_validation_extraction_and_upload(client, database, media_tools, tmp_path):
    ffmpeg, ffprobe = media_tools
    video = tmp_path / 'tiny.mp4'
    subprocess.run([
        ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=64x64:r=10',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000', '-t', '1',
        '-c:v', 'mpeg4', '-c:a', 'aac', str(video),
    ], check=True, capture_output=True, timeout=30)
    assert validate_video(video, ffprobe).duration_ms > 0
    audio = extract_audio(video, tmp_path / 'audio.wav', ffmpeg)
    import wave
    with wave.open(str(audio)) as stream:
        assert stream.getnchannels() == 1
        assert stream.getframerate() == 16000
    response = upload(client, video.read_bytes(), 'tiny.mp4')
    assert response.status_code == 202
    assert upload(client, b'not an MP4', 'spoofed.mp4').status_code == 400


def test_real_mp4_without_audio_is_rejected(client, database, media_tools, tmp_path):
    ffmpeg, _ = media_tools
    video = tmp_path / 'silent.mp4'
    subprocess.run([
        ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=64x64:r=10',
        '-t', '1', '-c:v', 'mpeg4', str(video),
    ], check=True, capture_output=True, timeout=30)
    response = upload(client, video.read_bytes(), 'silent.mp4')
    assert response.status_code == 400
    assert 'no audio stream' in response.json()['detail']


def test_video_migration_is_additive_and_repeatable(database):
    from conftest import ROOT
    with database() as connection:
        original = connection.execute('SELECT * FROM files ORDER BY id').fetchall()
    for _ in range(2):
        with database() as connection:
            connection.execute((ROOT / 'database/migrations/004_video_transcription.sql').read_text())
    with database() as connection:
        assert connection.execute('SELECT * FROM files ORDER BY id').fetchall() == original


def test_worker_recovers_and_processes_one_claimed_job(client, database, fake_video_tools, monkeypatch):
    from app import worker
    created = upload(client).json()
    monkeypatch.setattr(worker, 'get_connection', database)
    monkeypatch.setattr(worker, 'WORKER_LOCK_ID', 92845101)
    monkeypatch.setattr(worker.signal, 'signal', lambda *args: None)
    worker.run_worker(once=True)
    assert repository.get_job(created['job_id']).status == 'completed'


def test_second_worker_is_rejected(database, monkeypatch):
    from app import worker
    monkeypatch.setattr(worker, 'get_connection', database)
    monkeypatch.setattr(worker, 'WORKER_LOCK_ID', 92845102)
    monkeypatch.setattr(worker.signal, 'signal', lambda *args: None)
    with database() as lock_connection:
        lock_connection.execute('SELECT pg_advisory_lock(%s)', (worker.WORKER_LOCK_ID,))
        with pytest.raises(RuntimeError, match='already running'):
            worker.run_worker(once=True)


def test_video_storage_failure(client, uploads):
    uploads.write_text('Existing file at configured upload directory')
    assert upload(client).status_code == 500
    assert uploads.read_text() == 'Existing file at configured upload directory'


def test_worker_stops_if_failure_status_cannot_be_persisted(client, database, fake_video_tools, monkeypatch, caplog):
    upload(client)
    job = repository.claim_next_job()
    def fail_processing(*args, **kwargs):
        raise SpeechRecognitionError('Speech recognition failed.')
    def fail_status(*args, **kwargs):
        raise psycopg.OperationalError('private connection details')
    monkeypatch.setattr(transcription_service, 'transcribe_audio', fail_processing)
    monkeypatch.setattr(repository, 'fail_job', fail_status)
    with pytest.raises(RuntimeError, match='restart the worker'):
        transcription_service.process_video_job(job)
    assert 'private connection details' not in caplog.text
    assert job.storage_path.exists()
    assert not fake_video_tools[0].exists()
    # On the next start, recovery can identify this interrupted processing row.
    assert repository.get_job(job.job_id).status == 'processing'


def test_upload_cors_allows_existing_frontend(client):
    response = client.options('/videos/upload', headers={
        'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'


def test_supervised_worker_waits_for_existing_owner_before_recovery(monkeypatch):
    from app import worker
    events = []
    class LockConnection:
        autocommit = False
        attempts = 0
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, query, parameters=None):
            if 'pg_try_advisory_lock' in query:
                self.attempts += 1
                acquired = self.attempts > 1
                events.append('acquired' if acquired else 'busy')
                return type('Row', (), {'fetchone': lambda _: {'acquired': acquired}})()
            return None
    class Stopping:
        def is_set(self):
            return False
        def set(self):
            pass
        def wait(self, seconds):
            events.append('waiting')
            return False
    monkeypatch.setattr(worker, 'Event', Stopping)
    monkeypatch.setattr(worker.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(worker, 'get_connection', LockConnection)
    monkeypatch.setattr(worker, 'fail_interrupted_jobs', lambda: events.append('recover') or 0)
    monkeypatch.setattr(worker, 'claim_next_job', lambda: events.append('claim'))
    monkeypatch.setattr(worker, 'claim_presentation_job', lambda: None)
    monkeypatch.setattr(worker, 'claim_visual_job', lambda: None)
    worker.run_worker(once=True, wait_for_lock=True)
    assert events == ['busy', 'waiting', 'acquired', 'recover', 'claim']


def test_readable_download_is_independent_of_original_mp4(client, database, fake_video_tools, monkeypatch):
    from urllib.parse import quote

    filename = 'Möte – anteckningar.mp4'
    monkeypatch.setattr(transcription_service, 'transcribe_audio', lambda *args, **kwargs: TranscriptionResult('sv', [
        TranscriptSegment(0, 1000, 'Hej alla.  '),
        TranscriptSegment(1000, 2000, ' Välkomna till mötet.\n'),
        TranscriptSegment(5000, 6000, 'Nästa ämne.'),
    ]))
    created = upload(client, b'x' * 10000, filename).json()
    job = repository.claim_next_job()
    transcription_service.process_video_job(job)
    # Simulate future removal of this test's original: the text is self-contained.
    job.storage_path.unlink()
    response = client.get(f"/videos/{created['file_id']}/transcript/download")
    assert response.status_code == 200
    assert response.text == filename + '\n\nHej alla. Välkomna till mötet.\n\nNästa ämne.\n'
    assert response.content == response.text.encode('utf-8')
    assert len(response.content) < 10000
    assert "filename*=UTF-8''" + quote('Möte – anteckningar.txt', safe='') in response.headers['content-disposition']
    transcript = client.get(f"/videos/{created['file_id']}/transcript").json()
    assert len(transcript['paragraphs']) == 2
    result = client.get('/search', params={'q': 'Välkomna'}).json()['results'][0]
    assert result['file_id'] == created['file_id']
    assert result['segment_id'] in transcript['paragraphs'][0]
