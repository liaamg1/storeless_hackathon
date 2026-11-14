"""Real PostgreSQL claims and worker subprocesses use disposable schemas only."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
import pytest

from app.core import worker_context
from app.core.config import get_worker_settings
from app.repositories import job_repository as jobs, upload_repository
from app.services import document_jobs


def store(database, uploads, name, size, kind, status='queued', slot=None, options=None):
    uploads.mkdir(exist_ok=True)
    path = uploads / name
    path.write_bytes(b'x' * size)
    with database() as c:
        file_id = c.execute(
            'INSERT INTO files(filename,size_bytes,sha256,storage_path,processing_options) VALUES(%s,%s,%s,%s,%s) RETURNING id',
            (name, size, 'a1' * 32, str(path), Jsonb(options) if options else None),
        ).fetchone()['id']
        job_id = c.execute(
            'INSERT INTO processing_jobs(file_id,job_type,status,worker_slot) VALUES(%s,%s,%s,%s) RETURNING id',
            (file_id, kind, status, slot),
        ).fetchone()['id']
    return file_id, job_id, path


def test_worker_defaults_and_configuration(monkeypatch):
    for key in ('TRANSCRIPTION_WORKERS', 'DOCUMENT_WORKERS', 'VISUAL_WORKERS'):
        monkeypatch.delenv(key, raising=False)
    s = get_worker_settings()
    assert (s.transcription, s.document, s.visual) == (1, 2, 1)
    monkeypatch.setenv('DOCUMENT_WORKERS', '3')
    assert get_worker_settings().document == 3
    monkeypatch.setenv('TRANSCRIPTION_WORKERS', '0')
    with pytest.raises(ValueError):
        get_worker_settings()


def test_smallest_first_across_document_tasks_and_no_duplicate_claims(database, uploads):
    large = store(database, uploads, 'large.pdf', 500, 'pdf_text')
    medium = store(database, uploads, 'medium.pdf', 100, 'presentation_analysis')
    small = store(database, uploads, 'small.pdf', 20, 'pdf_text')
    assert jobs.claim('document').file_id == small[0]
    assert jobs.claim('document').file_id == medium[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda _: jobs.claim('document'), range(2)))
    assert len([job for job in claimed if job]) == 1
    assert next(job for job in claimed if job).file_id == large[0]


def test_transcription_and_visual_sizes_and_dependencies(database, uploads):
    large = store(database, uploads, 'large.mp4', 400, 'video_transcription')
    small = store(database, uploads, 'small.mp4', 10, 'video_transcription')
    with database() as c:
        c.execute("INSERT INTO processing_jobs(file_id,job_type) VALUES(%s,'video_visuals')", (small[0],))
    assert jobs.claim('visual') is None
    assert jobs.claim('transcription').file_id == small[0]
    assert jobs.claim('transcription').file_id == large[0]
    with database() as c:
        c.execute("UPDATE processing_jobs SET status='completed' WHERE id=%s", (small[1],))
    assert jobs.claim('visual').file_id == small[0]


def test_slides_wait_for_pdf_text_and_failed_dependency_does_not_run(database, uploads):
    file_id, job_id, _ = store(database, uploads, 'deck.pdf', 30, 'pdf_text')
    with database() as c:
        c.execute(
            "INSERT INTO processing_jobs(file_id,job_type) VALUES(%s,'presentation_analysis')", (file_id,)
        )
    assert jobs.claim('document').job_type == 'pdf_text'
    assert jobs.claim('document') is None
    with database() as c:
        c.execute("UPDATE processing_jobs SET status='failed' WHERE id=%s", (job_id,))
    assert jobs.claim('document') is None
    with database() as c:
        c.execute("UPDATE processing_jobs SET status='completed' WHERE id=%s", (job_id,))
    assert jobs.claim('document').job_type == 'presentation_analysis'


def test_scoped_recovery_preserves_other_live_workers(database, uploads):
    own = store(database, uploads, 'own.pdf', 10, 'pdf_text', 'processing', 'document:0')
    other = store(database, uploads, 'other.pdf', 20, 'pdf_text', 'processing', 'document:1')
    video = store(database, uploads, 'video.mp4', 30, 'video_transcription', 'processing', 'transcription:0')
    assert jobs.recover('document', 'document:0') == 1
    with database() as c:
        states = {row['id']: row['status'] for row in c.execute('SELECT id,status FROM processing_jobs')}
    assert states[own[1]] == 'failed' and states[other[1]] == states[video[1]] == 'processing'


def test_progress_is_visible_before_atomic_pdf_commit(client, database, uploads, monkeypatch):
    from app.processors.pdf_processor import ExtractedPage

    file_id, job_id, _ = store(database, uploads, 'measurable.pdf', 20, 'pdf_text', options=['pdf_text'])
    job = jobs.claim('document')
    waiting = Event()
    release = Event()

    def pages(path, *, on_progress):
        on_progress(0, 2)
        yield ExtractedPage(1, 'first page')
        on_progress(1, 2)
        waiting.set()
        assert release.wait(10)
        yield ExtractedPage(2, 'second page')
        on_progress(2, 2)

    monkeypatch.setattr(document_jobs, 'iter_pdf_pages', pages)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(document_jobs.process_document_job, job)
        try:
            assert waiting.wait(5)
            state = client.get(f'/uploads/{file_id}').json()
            assert state['progress_percent'] == 50 and state['progress_total'] == 2
            assert state['progress_scope'] == 'current_step'
            with database() as c:
                assert (
                    c.execute(
                        'SELECT count(*) AS n FROM document_pages WHERE file_id=%s', (file_id,)
                    ).fetchone()['n']
                    == 0
                )
        finally:
            release.set()
        future.result(timeout=10)
    state = client.get(f'/uploads/{file_id}').json()
    assert state['status'] == 'completed' and state['progress_percent'] == 100


def test_stale_progress_is_rejected_and_retry_clears_counts(database, uploads):
    file_id, job_id, _ = store(database, uploads, 'owned.pdf', 20, 'pdf_text', 'processing', 'document:0')
    old, new = uuid4(), uuid4()
    with database() as c:
        c.execute('UPDATE processing_jobs SET worker_id=%s WHERE id=%s', (new, job_id))
    with worker_context.bind(None, 'document:0', old):
        jobs.progress(job_id, 4, 10, 'pages')
    with database() as c:
        assert (
            c.execute('SELECT progress_current FROM processing_jobs WHERE id=%s', (job_id,)).fetchone()[
                'progress_current'
            ]
            is None
        )
        c.execute(
            "UPDATE processing_jobs SET status='failed',progress_current=4,progress_total=10 WHERE id=%s",
            (job_id,),
        )
    assert upload_repository.queue(file_id, 'pdf_text')
    with database() as c:
        row = c.execute('SELECT * FROM processing_jobs WHERE id=%s', (job_id,)).fetchone()
    assert row['worker_id'] is None and row['progress_current'] is None


def test_lost_ownership_session_cannot_commit_results(database, uploads, monkeypatch):
    from app.core.database import get_connection

    store(database, uploads, 'fenced.pdf', 20, 'pdf_text')
    monkeypatch.setattr(jobs, 'get_connection', get_connection)
    with database() as session:
        session.autocommit = True
        with worker_context.bind(session, 'document:0', uuid4()):
            job = jobs.claim('document')
            with database() as admin:
                admin.execute('SELECT pg_terminate_backend(%s)', (session.info.backend_pid,))
            with pytest.raises(psycopg.Error):
                with get_connection() as c:
                    c.execute("UPDATE processing_jobs SET status='completed' WHERE id=%s", (job.job_id,))
    monkeypatch.setattr(jobs, 'get_connection', database)
    assert jobs.recover('document', 'document:0') == 1


def test_percentage_is_measured_not_stage_weighted():
    assert jobs.percentage({'status': 'processing'}) is None
    assert jobs.percentage({'status': 'processing', 'progress_current': 3, 'progress_total': 8}) == 37
    assert jobs.percentage({'status': 'failed', 'progress_current': 3, 'progress_total': 8}) == 37
    assert jobs.percentage({'status': 'completed'}) == 100


def test_real_document_worker_finishes_while_video_worker_is_busy(client, database, uploads, pdf_bytes):
    video = store(database, uploads, 'busy.mp4', 200, 'video_transcription')
    pdf = store(database, uploads, 'parallel.pdf', 20, 'pdf_text')
    pdf[2].write_bytes(pdf_bytes(('Parallel document while video remains busy',)))
    with database() as c:
        dsn = c.info.dsn
    env = {
        **os.environ,
        'DATABASE_URL': dsn,
        'UPLOAD_DIR': str(uploads),
        'AUTO_START_TRANSCRIPTION_WORKER': 'false',
    }
    # Replace only inference with a controlled busy stage; the processes, queue,
    # ownership sessions and PDF parser are real and independent.
    code = """import time
from app import worker
from app.repositories.job_repository import progress
from app.repositories.transcription_repository import fail_job
def busy(job):
    progress(job.job_id,1,10,'audio_ms')
    time.sleep(30)
worker.process_video_job=busy
worker.run_slot_worker('transcription',7,once=True,wait_for_lock=False)
"""
    process = subprocess.Popen(
        [sys.executable, '-c', code], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with database() as c:
                state = c.execute('SELECT status FROM processing_jobs WHERE id=%s', (video[1],)).fetchone()[
                    'status'
                ]
            if state == 'processing':
                break
            if process.poll() is not None:
                raise AssertionError(process.stderr.read().decode())
            time.sleep(0.05)
        assert state == 'processing'
        assert client.get('/health').status_code == 200
        second = subprocess.run(
            [sys.executable, '-m', 'app.worker', '--kind', 'transcription', '--slot', '7', '--once'],
            env=env,
            capture_output=True,
            timeout=10,
        )
        assert second.returncode == 1  # the occupied video slot cannot admit another inference
        result = subprocess.run(
            [sys.executable, '-m', 'app.worker', '--kind', 'document', '--slot', '7', '--once'],
            env=env,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr.decode()
        with database() as c:
            assert (
                c.execute('SELECT status FROM processing_jobs WHERE id=%s', (pdf[1],)).fetchone()['status']
                == 'completed'
            )
            assert (
                c.execute('SELECT status FROM processing_jobs WHERE id=%s', (video[1],)).fetchone()['status']
                == 'processing'
            )
    finally:
        process.kill()
        process.wait(timeout=5)
        process.stderr.close()


def test_failed_pdf_marks_blocked_slides_failed_and_retry_is_clean(database, uploads):
    from app.repositories.transcription_repository import fail_job

    file_id, job_id, _ = store(database, uploads, 'dependency.pdf', 20, 'pdf_text')
    with database() as c:
        c.execute(
            "INSERT INTO processing_jobs(file_id,job_type) VALUES(%s,'presentation_analysis')", (file_id,)
        )
    jobs.claim('document')
    fail_job(job_id, 'PDF failed')
    with database() as c:
        assert (
            c.execute(
                "SELECT status FROM processing_jobs WHERE file_id=%s AND job_type='presentation_analysis'",
                (file_id,),
            ).fetchone()['status']
            == 'failed'
        )
    upload_repository.queue(file_id, 'pdf_text')
    upload_repository.queue(file_id, 'presentation_analysis')
    assert jobs.claim('document').job_type == 'pdf_text'
    assert jobs.claim('document') is None
