import hashlib
from pathlib import Path

from app.processors.audio_extractor import VideoMetadata
from app.repositories import transcription_repository, upload_repository
from app.services import transcription_service


def test_completed_video_reupload_returns_existing_job_without_new_recognition(
    client, database, uploads, monkeypatch
):
    monkeypatch.setattr(transcription_service, 'validate_video', lambda *args: VideoMetadata(1000))
    content = b'repeated recording with completed transcript'
    first = client.post('/videos/upload', files={'file': ('first.mp4', content, 'video/mp4')}).json()
    with database() as connection:
        connection.execute("UPDATE processing_jobs SET status='completed' WHERE id=%s", (first['job_id'],))
        connection.execute(
            "INSERT INTO transcript_segments(file_id,start_ms,end_ms,text) VALUES(%s,0,1000,'reusable speech')",
            (first['file_id'],),
        )

    def forbidden(*args):
        raise AssertionError('Reused recordings must not be probed or recognized again')

    monkeypatch.setattr(transcription_service, 'validate_video', forbidden)
    second = client.post('/videos/upload', files={'file': ('again.mp4', content, 'video/mp4')})
    assert second.status_code == 202, second.text
    assert second.json()['reused'] and second.json()['status'] == 'completed'
    assert second.json()['file_id'] == first['file_id'] and second.json()['job_id'] == first['job_id']
    assert len(list(uploads.glob('*.mp4'))) == 1
    assert (
        client.get(f"/videos/{first['file_id']}/transcript").json()['segments'][0]['text']
        == 'reusable speech'
    )


def test_pending_upload_and_repository_race_share_one_job(client, database, uploads, monkeypatch):
    monkeypatch.setattr(transcription_service, 'validate_video', lambda *args: VideoMetadata(1000))
    content = b'pending identical upload'
    digest = hashlib.sha256(content).hexdigest()
    first = client.post('/videos/upload', files={'file': ('one.mp4', content, 'video/mp4')}).json()
    second = client.post('/videos/upload', files={'file': ('two.mp4', content, 'video/mp4')}).json()
    assert second['reused'] and second['file_id'] == first['file_id']
    # Exercise the locked final insertion check independently of the service fast path.
    path = uploads / 'race.mp4'
    path.write_bytes(content)
    result = transcription_repository.create_video_job('race.mp4', len(content), digest, path, 1000)
    assert result.reused and result.file_id == first['file_id']
    with database() as connection:
        assert (
            connection.execute(
                "SELECT count(*) AS n FROM processing_jobs WHERE job_type='video_transcription'"
            ).fetchone()['n']
            == 1
        )


def test_lookup_prefers_completed_over_failed_or_missing(database, uploads):
    uploads.mkdir()
    content = b'preferred completed recording'
    digest = hashlib.sha256(content).hexdigest()
    ids = []
    for number, status in enumerate(('failed', 'completed', 'completed')):
        path = uploads / f'{number}.mp4'
        if number != 1:
            path.write_bytes(content)
        with database() as connection:
            file_id = connection.execute(
                "INSERT INTO files(filename,size_bytes,sha256,storage_path,file_type) VALUES(%s,%s,%s,%s,'video') RETURNING id",
                (path.name, len(content), digest, str(path)),
            ).fetchone()['id']
            connection.execute(
                "INSERT INTO processing_jobs(file_id,job_type,status) VALUES(%s,'video_transcription',%s)",
                (file_id, status),
            )
        ids.append(file_id)
    assert upload_repository.find_existing(digest, len(content), '.mp4') == ids[2]


def test_concurrent_repository_uploads_serialize_identical_jobs(database, uploads):
    from concurrent.futures import ThreadPoolExecutor

    uploads.mkdir()
    content = b'concurrent identical recording'
    digest = hashlib.sha256(content).hexdigest()
    paths = [uploads / f'parallel-{number}.mp4' for number in range(2)]
    for path in paths:
        path.write_bytes(content)

    def create(path):
        return transcription_repository.create_video_job(path.name, len(content), digest, path, 1000)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, paths))
    assert results[0].file_id == results[1].file_id
    assert sorted(result.reused for result in results) == [False, True]
    with database() as connection:
        assert connection.execute("SELECT count(*) AS n FROM processing_jobs").fetchone()['n'] == 1
