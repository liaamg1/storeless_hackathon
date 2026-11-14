"""Verified cleanup operates only on files in the disposable test upload directory."""

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.services import duplicate_cleanup as service


@pytest.fixture
def copies(database, uploads):
    uploads.mkdir(exist_ok=True)
    content = b'actual identical originals for verified cleanup'
    ids, paths = [], []
    for number in range(3):
        path = uploads / f'copy-{number}.mp4'
        path.write_bytes(content)
        with database() as connection:
            row = connection.execute(
                """INSERT INTO files(filename,size_bytes,sha256,storage_path,file_type)
                VALUES(%s,%s,%s,%s,'video') RETURNING id""",
                (path.name, len(content), hashlib.sha256(content).hexdigest(), str(path)),
            ).fetchone()
        ids.append(row['id'])
        paths.append(path)
    return ids, paths, content


def cleanup(client, ids, keeper=None, confirmed=True):
    return client.post(
        '/duplicates/cleanup', json={'keeper_id': keeper or ids[0], 'member_ids': ids, 'confirmed': confirmed}
    )


def test_verified_cleanup_keeps_one_copy_and_records_actual_bytes(client, database, copies):
    ids, paths, content = copies
    result = cleanup(client, ids)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['status'] == 'resolved' and data['removed_bytes'] == 2 * len(content)
    assert data['measurement_complete'] and data['removed_ids'] == ids[1:]
    assert paths[0].read_bytes() == content and not paths[1].exists() and not paths[2].exists()
    assert client.get('/duplicates').json()['groups'] == []
    assert client.get('/duplicates/resolutions').json() == [data]
    assert 'storage_path' not in result.text and 'staged_files' not in result.text
    assert client.post(f"/duplicates/resolutions/{data['id']}/finish").json() == data
    assert cleanup(client, ids).status_code == 409
    # A new physical copy is a new unresolved case; old resolved rows stay excluded.
    path = paths[1]
    path.write_bytes(content)
    with database() as connection:
        connection.execute(
            "INSERT INTO files(filename,size_bytes,sha256,storage_path) VALUES('new.mp4',%s,%s,%s)",
            (len(content), hashlib.sha256(content).hexdigest(), str(path)),
        )
    assert client.get('/duplicates').json()['summary']['redundant_copies'] == 1


@pytest.mark.parametrize(
    'reason', ['confirmation', 'stale', 'missing', 'changed', 'active', 'results', 'outside', 'symlink']
)
def test_cleanup_refuses_unverified_or_unsafe_case(client, database, copies, reason, tmp_path):
    ids, paths, content = copies
    selection = ids
    if reason == 'stale':
        selection = ids[:2]
    if reason == 'missing':
        paths[0].unlink()
    if reason == 'changed':
        paths[1].write_bytes(b'x' * len(content))
    if reason in ('active', 'results'):
        with database() as connection:
            connection.execute(
                "INSERT INTO processing_jobs(file_id,job_type,status) VALUES(%s,'video_transcription',%s)",
                (ids[1], 'processing' if reason == 'active' else 'completed'),
            )
    if reason == 'outside':
        external = tmp_path / 'outside.mp4'
        external.write_bytes(content)
        with database() as connection:
            connection.execute('UPDATE files SET storage_path=%s WHERE id=%s', (str(external), ids[1]))
    if reason == 'symlink':
        paths[1].unlink()
        paths[1].symlink_to(paths[0])
    result = cleanup(client, selection, confirmed=reason != 'confirmation')
    assert result.status_code == 409, result.text
    assert paths[2].read_bytes() == content
    if reason != 'missing':
        assert paths[0].read_bytes() == content
    with database() as connection:
        assert connection.execute('SELECT count(*) AS n FROM duplicate_resolutions').fetchone()['n'] == 0
        assert (
            connection.execute(
                'SELECT count(*) AS n FROM files WHERE original_removed_at IS NOT NULL'
            ).fetchone()['n']
            == 0
        )


def test_keeper_with_completed_results_preserves_transcript(client, database, copies):
    ids, paths, content = copies
    with database() as connection:
        connection.execute(
            "INSERT INTO processing_jobs(file_id,job_type,status) VALUES(%s,'video_transcription','completed')",
            (ids[1],),
        )
        connection.execute(
            "INSERT INTO transcript_segments(file_id,start_ms,end_ms,text) VALUES(%s,0,1000,'failures')",
            (ids[1],),
        )
    group = client.get('/duplicates').json()['groups'][0]
    assert group['files'][1]['completed_operations'] == ['video_transcription']
    assert cleanup(client, ids, keeper=ids[1]).status_code == 200
    transcript = client.get(f'/videos/{ids[1]}/transcript').json()
    assert transcript['segments'][0]['text'] == 'failures'
    assert paths[1].read_bytes() == content
    assert client.get('/search', params={'q': 'failures'}).json()['results'][0]['file_id'] == ids[1]


def test_failed_database_commit_restores_all_staged_originals(client, database, copies):
    ids, paths, content = copies
    with database() as connection:
        connection.execute('ALTER TABLE duplicate_resolutions ADD CONSTRAINT reject_cleanup CHECK(false)')
    assert cleanup(client, ids).status_code == 500
    assert all(path.read_bytes() == content for path in paths)


def test_pending_purge_is_visible_and_retryable(client, database, copies, monkeypatch):
    ids, paths, content = copies
    original = Path.unlink

    def blocked(path, *args, **kwargs):
        if '.cleanup' in path.parts and path.suffix == '.mp4':
            raise PermissionError('QA injected failure')
        return original(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, 'unlink', blocked)
        result = cleanup(client, ids).json()
    assert result['status'] == 'pending_purge' and result['removed_bytes'] == 0
    assert paths[0].read_bytes() == content
    result = client.post(f"/duplicates/resolutions/{result['id']}/finish").json()
    assert result['status'] == 'resolved' and result['removed_bytes'] == len(content) * 2


def test_hard_linked_originals_do_not_claim_freed_bytes(client, database, copies):
    ids, paths, content = copies
    for path in paths[1:]:
        path.unlink()
        os.link(paths[0], path)
    result = cleanup(client, ids).json()
    assert result['status'] == 'resolved' and result['removed_bytes'] == 0
    assert paths[0].read_bytes() == content


def test_interrupted_staging_recovers_before_worker_runs(database, copies, uploads):
    ids, paths, content = copies
    folder = uploads / '.cleanup' / str(uuid4())
    folder.mkdir(parents=True)
    staged = folder / paths[1].name
    (folder / 'journal.json').write_text(
        json.dumps(
            {
                'sha256': hashlib.sha256(content).hexdigest(),
                'files': [{'file_id': ids[1], 'original': str(paths[1]), 'staged': str(staged)}],
            }
        )
    )
    paths[1].rename(staged)
    service.recover_staging()
    assert all(path.read_bytes() == content for path in paths)
    assert not folder.exists()


def test_cleanup_does_not_wait_on_a_locked_worker_job(client, database, copies):
    from concurrent.futures import ThreadPoolExecutor

    ids, paths, content = copies
    with database() as connection:
        connection.execute(
            "INSERT INTO processing_jobs(file_id,job_type,status) VALUES(%s,'video_transcription','completed')",
            (ids[0],),
        )
    with database() as locked:
        locked.execute('SELECT id FROM processing_jobs WHERE file_id=%s FOR UPDATE', (ids[0],))
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(cleanup, client, ids).result(timeout=5)
    assert result.status_code == 409
    assert all(path.read_bytes() == content for path in paths)


def test_pending_purge_rechecks_keeper_and_never_credits_unknown_bytes(client, database, copies, monkeypatch):
    ids, paths, content = copies
    original = Path.unlink

    def blocked(path, *args, **kwargs):
        if '.cleanup' in path.parts and path.suffix == '.mp4':
            raise PermissionError('QA injected failure')
        return original(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, 'unlink', blocked)
        result = cleanup(client, ids).json()
    paths[0].write_bytes(b'x' * len(content))
    assert client.post(f"/duplicates/resolutions/{result['id']}/finish").status_code == 409
    paths[0].write_bytes(content)
    with database() as connection:
        private = connection.execute(
            'SELECT staged_files FROM duplicate_resolutions WHERE id=%s', (result['id'],)
        ).fetchone()
    Path(private['staged_files'][0]['staged']).unlink()
    result = client.post(f"/duplicates/resolutions/{result['id']}/finish").json()
    assert result['status'] == 'resolved' and not result['measurement_complete']
    assert result['removed_bytes'] == len(content)
    assert paths[0].read_bytes() == content


def test_retired_id_processing_redirects_to_keeper(client, database, copies):
    ids, paths, content = copies
    with database() as connection:
        for file_id in ids:
            connection.execute(
                "INSERT INTO processing_jobs(file_id,job_type,status) VALUES(%s,'video_transcription','completed')",
                (file_id,),
            )
    assert cleanup(client, ids).status_code == 200
    response = client.post(f'/uploads/{ids[1]}/process', json={'operations': ['transcribe']})
    assert response.status_code == 202, response.text
    assert response.json()['file_id'] == ids[0]
    assert paths[0].read_bytes() == content
