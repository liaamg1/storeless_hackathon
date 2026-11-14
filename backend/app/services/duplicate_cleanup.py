"""Explicit duplicate cleanup: verify a keeper, stage removals, commit, then purge.

Only original upload files can be removed. Derived text/images and metadata are
preserved. Pending purges remain visible and retryable after interruption.
"""

import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from psycopg.errors import LockNotAvailable
from psycopg.types.json import Jsonb

from app.core.config import get_settings
from app.repositories import duplicate_repository as repository


class CleanupConflict(ValueError):
    pass


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(64 * 1024):
            value.update(chunk)
    return value.hexdigest()


def original_path(file: dict) -> Path:
    root = get_settings().upload_dir.resolve()
    path = Path(file['storage_path']) if file.get('storage_path') else None
    if (
        path is None
        or path.is_symlink()
        or path.resolve().parent != root
        or path.suffix.lower() not in ('.pdf', '.pptx', '.mp4')
    ):
        raise CleanupConflict('This original is not a managed local upload. No files were removed.')
    if not path.is_file():
        raise CleanupConflict('An original is missing. Refresh the case before cleanup.')
    return path


def verify(file: dict, expected: str, size: int) -> Path:
    path = original_path(file)
    if path.stat().st_size != size or digest(path) != expected.lower():
        raise CleanupConflict('File bytes changed or no longer match. No cleanup is authorized.')
    return path


def public(row: dict) -> dict:
    return {
        key: row[key]
        for key in (
            'id',
            'keeper_id',
            'removed_ids',
            'status',
            'removed_bytes',
            'measurement_complete',
            'created_at',
            'completed_at',
        )
    }


def recover_staging() -> None:
    """Restore uncommitted moves after a crash; committed purges require review.

    The journal is written before the first rename. The content lock prevents a
    second API process from recovering a cleanup whose transaction is still live.
    """
    root = get_settings().upload_dir.resolve()
    for journal in (root / '.cleanup').glob('*/journal.json'):
        if journal.is_symlink() or journal.parent.is_symlink():
            continue
        data = json.loads(journal.read_text())
        resolution_id = UUID(journal.parent.name)
        with repository.get_connection() as connection:
            with connection.transaction():
                locked = connection.execute(
                    'SELECT pg_try_advisory_xact_lock(%s) AS locked',
                    (repository.content_lock_key(data['sha256']),),
                ).fetchone()['locked']
                if not locked:
                    continue
                if connection.execute(
                    'SELECT id FROM duplicate_resolutions WHERE id=%s', (resolution_id,)
                ).fetchone():
                    continue
                for item in data['files']:
                    source, target = Path(item['staged']), Path(item['original'])
                    if (
                        source.resolve().parent != journal.parent.resolve()
                        or target.resolve().parent != root
                        or source.is_symlink()
                        or target.is_symlink()
                    ):
                        raise CleanupConflict('An interrupted cleanup needs manual path review.')
                    if not source.is_file():
                        if not target.is_file():
                            raise CleanupConflict(
                                'An interrupted cleanup is missing a copy; remaining files are preserved.'
                            )
                        continue
                    file = connection.execute(
                        'SELECT * FROM files WHERE id=%s FOR UPDATE', (item['file_id'],)
                    ).fetchone()
                    if (
                        not file
                        or file['original_removed_at'] is not None
                        or str(target) != file['storage_path']
                    ):
                        raise CleanupConflict('An interrupted cleanup needs manual file review.')
                    if target.exists():
                        raise CleanupConflict('An interrupted cleanup cannot overwrite an existing original.')
                    if (
                        source.stat().st_size != file['size_bytes']
                        or digest(source) != file['sha256'].lower()
                    ):
                        raise CleanupConflict(
                            'An interrupted cleanup contains changed bytes; copies are preserved.'
                        )
                    source.rename(target)
                journal.unlink()
                journal.parent.rmdir()


def history() -> list[dict]:
    recover_staging()
    with repository.get_connection() as connection:
        return [
            public(row)
            for row in connection.execute(
                'SELECT * FROM duplicate_resolutions ORDER BY created_at DESC'
            ).fetchall()
        ]


def cleanup(keeper_id: int, member_ids: list[int], confirmed: bool) -> dict:
    if not confirmed or len(set(member_ids)) < 2 or keeper_id not in member_ids:
        raise CleanupConflict('Choose a retained copy and explicitly confirm removal of the other copies.')
    recover_staging()
    staged = []
    resolution_id = uuid4()
    folder = get_settings().upload_dir / '.cleanup' / str(resolution_id)
    committed = False
    try:
        with repository.get_connection() as connection:
            with connection.transaction():
                keeper = connection.execute('SELECT * FROM files WHERE id=%s', (keeper_id,)).fetchone()
                if not keeper or keeper['original_removed_at'] is not None:
                    raise CleanupConflict('The selected keeper is no longer an active original.')
                connection.execute(
                    'SELECT pg_advisory_xact_lock(%s)', (repository.content_lock_key(keeper['sha256']),)
                )
                files = connection.execute(
                    '''SELECT * FROM files WHERE lower(sha256)=%s AND size_bytes=%s
                    AND original_removed_at IS NULL ORDER BY id FOR UPDATE''',
                    (keeper['sha256'].lower(), keeper['size_bytes']),
                ).fetchall()
                if {file['id'] for file in files} != set(member_ids):
                    raise CleanupConflict('The duplicate list changed. Refresh and review it again.')
                if connection.execute(
                    "SELECT id FROM duplicate_resolutions WHERE sha256=%s AND status='pending_purge'",
                    (keeper['sha256'].lower(),),
                ).fetchone():
                    raise CleanupConflict('Finish the pending cleanup for this content first.')
                # Lock existing jobs; new job inserts also wait for the file-row locks.
                try:
                    jobs = connection.execute(
                        'SELECT id,file_id,job_type,status FROM processing_jobs WHERE file_id=ANY(%s) FOR UPDATE NOWAIT',
                        (member_ids,),
                    ).fetchall()
                except LockNotAvailable as exc:
                    raise CleanupConflict(
                        'A related job is changing. Wait for it to finish and refresh.'
                    ) from exc
                if any(job['status'] in ('queued', 'processing') for job in jobs):
                    raise CleanupConflict('A related processing job is active. Wait for it to finish.')
                # Keep completed, expensive analysis on the active original so a later
                # identical upload can reuse it without scheduling recognition again.
                preserved_types = {'video_transcription', 'video_visuals', 'presentation_analysis'}
                completed = {
                    (job['file_id'], job['job_type']) for job in jobs if job['status'] == 'completed'
                }
                for operation in preserved_types:
                    ready = sorted(file_id for file_id, kind in completed if kind == operation)
                    if ready and (keeper_id, operation) not in completed:
                        raise CleanupConflict(
                            f'Choose a keeper with completed {operation.replace("_", " ")} '
                            f'to preserve existing results (File #{ready[0]}).'
                        )
                keeper = next(file for file in files if file['id'] == keeper_id)
                keep_path = verify(keeper, keeper['sha256'], keeper['size_bytes'])
                for file in files:
                    if file['id'] == keeper_id:
                        continue
                    path = verify(file, keeper['sha256'], keeper['size_bytes'])
                    if path.resolve() == keep_path.resolve():
                        # Two metadata rows may already share one physical upload.
                        continue
                    if any(item['original'] == str(path) for item in staged):
                        continue
                    staged.append(
                        {
                            'file_id': file['id'],
                            'original': str(path),
                            'staged': str(folder / path.name),
                            'size': path.stat().st_size,
                            'purged': False,
                        }
                    )
                # Validate everything before moving anything. Rename stays on the same volume.
                folder.mkdir(parents=True, exist_ok=False)
                with (folder / 'journal.json').open('x') as journal:
                    json.dump({'sha256': keeper['sha256'], 'files': staged}, journal)
                    journal.flush()
                    os.fsync(journal.fileno())
                for item in staged:
                    Path(item['original']).rename(item['staged'])
                removed = sorted(set(member_ids) - {keeper_id})
                connection.execute(
                    'UPDATE files SET duplicate_of=%s,original_removed_at=NOW() WHERE id=ANY(%s)',
                    (keeper_id, removed),
                )
                connection.execute(
                    '''INSERT INTO duplicate_resolutions(id,sha256,file_size_bytes,keeper_id,removed_ids,staged_files,status)
                    VALUES(%s,%s,%s,%s,%s,%s,'pending_purge')''',
                    (
                        resolution_id,
                        keeper['sha256'].lower(),
                        keeper['size_bytes'],
                        keeper_id,
                        Jsonb(removed),
                        Jsonb(staged),
                    ),
                )
            committed = True
    finally:
        if not committed:
            for item in staged:
                path = Path(item['staged'])
                if path.is_file() and not Path(item['original']).exists():
                    path.rename(item['original'])
            journal = folder / 'journal.json'
            if journal.is_file():
                journal.unlink()
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
    return finish(resolution_id)


def finish(resolution_id: UUID) -> dict:
    with repository.get_connection() as connection:
        with connection.transaction():
            row = connection.execute(
                'SELECT * FROM duplicate_resolutions WHERE id=%s FOR UPDATE', (resolution_id,)
            ).fetchone()
            if not row:
                raise CleanupConflict('Cleanup case not found.')
            if row['status'] == 'resolved':
                return public(row)
            connection.execute(
                'SELECT pg_advisory_xact_lock(%s)', (repository.content_lock_key(row['sha256']),)
            )
            keeper = connection.execute(
                'SELECT * FROM files WHERE id=%s FOR UPDATE', (row['keeper_id'],)
            ).fetchone()
            if not keeper or keeper['original_removed_at'] is not None:
                raise CleanupConflict('The keeper is unavailable. Pending copies have been preserved.')
            verify(keeper, row['sha256'], row['file_size_bytes'])
            removed_bytes = row['removed_bytes']
            complete = row['measurement_complete']
            items = row['staged_files']
            pending = False
            root = (get_settings().upload_dir / '.cleanup' / str(row['id'])).resolve()
            for item in items:
                if item['purged']:
                    continue
                path = Path(item['staged'])
                if path.resolve().parent != root or path.is_symlink():
                    raise CleanupConflict('Invalid cleanup path. Pending copies have been preserved.')
                try:
                    if path.is_file():
                        stat = path.stat()
                        # Hard-linked data is not freed until its final physical link disappears.
                        amount = stat.st_size if stat.st_nlink == 1 else 0
                        path.unlink()
                        removed_bytes += amount
                    else:
                        # An interrupted unlink cannot be credited without recorded confirmation.
                        complete = False
                    item['purged'] = True
                except OSError:
                    pending = True
            status = 'pending_purge' if pending else 'resolved'
            result = connection.execute(
                '''UPDATE duplicate_resolutions SET staged_files=%s,status=%s,
                removed_bytes=%s,measurement_complete=%s,completed_at=CASE WHEN %s='resolved' THEN NOW() ELSE NULL END
                WHERE id=%s RETURNING *''',
                (Jsonb(items), status, removed_bytes, complete, status, resolution_id),
            ).fetchone()
    journal = root / 'journal.json'
    if status == 'resolved' and journal.is_file():
        journal.unlink()
    if root.is_dir() and not any(root.iterdir()):
        root.rmdir()
    return public(result)
