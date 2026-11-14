"""Single local transcription worker: run `python -m app.worker` from backend/."""

import argparse
import logging
import signal
from threading import Event

from app.core.database import get_connection
from app.repositories.transcription_repository import claim_next_job, fail_interrupted_jobs
from app.services.transcription_service import process_video_job
from app.repositories.presentation_repository import claim_presentation_job
from app.services.presentation_service import process_presentation_job
from app.repositories.visual_repository import claim as claim_visual_job
from app.services.visual_service import process_visual_job

logger = logging.getLogger(__name__)
WORKER_LOCK_ID = 72815041


def run_worker(once: bool = False, wait_for_lock: bool = False) -> None:
    """Persist stages in PostgreSQL while keeping inference outside HTTP requests.

    A session advisory lock permits only one worker for this local demo. Holding it
    allows restart recovery to safely identify interrupted jobs without a heartbeat
    system or accidentally failing another live worker's job.
    """
    stopping = Event()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signal_number, lambda *_: stopping.set())
    with get_connection() as lock_connection:
        lock_connection.autocommit = True
        waiting_logged = False
        while True:
            acquired = lock_connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired",
                (WORKER_LOCK_ID,),
            ).fetchone()["acquired"]
            if acquired:
                break
            if not wait_for_lock:
                raise RuntimeError("A transcription worker is already running for this database.")
            if not waiting_logged:
                logger.info("worker_waiting_for_lock")
                waiting_logged = True
            if stopping.wait(2):
                return
        from app.core.worker_context import bind
        from uuid import uuid4

        with bind(lock_connection, 'legacy:0', uuid4()):
            interrupted = fail_interrupted_jobs()
            logger.info("worker_started interrupted_jobs=%s", interrupted)
            while not stopping.is_set():
                try:
                    # A lost lock session must stop this worker before it claims more work.
                    lock_connection.execute("SELECT 1")
                    job = claim_next_job()
                    if job:
                        process_video_job(job)
                    else:
                        presentation_job = claim_presentation_job()
                        if presentation_job:
                            process_presentation_job(presentation_job)
                        else:
                            visual_job = claim_visual_job()
                            if visual_job:
                                process_visual_job(visual_job)
                            else:
                                from app.repositories import job_repository
                                from app.services.document_jobs import process_document_job

                                auxiliary = job_repository.claim('document')
                                if auxiliary:
                                    if auxiliary.job_type == 'presentation_analysis':
                                        process_presentation_job(auxiliary)
                                    else:
                                        process_document_job(auxiliary)
                                elif not once:
                                    stopping.wait(2)
                    if once:
                        return
                except Exception as exc:
                    logger.error("worker_database_failure error_type=%s", type(exc).__name__)
                    # Exit instead of continuing without the exclusivity guarantee.
                    raise RuntimeError(
                        "Worker stopped after a database failure; restart it to recover jobs."
                    ) from None


def run_slot_worker(kind: str, slot: int, once: bool = False, wait_for_lock: bool = True) -> None:
    """One process per stable slot; a DB session fences every artifact commit."""
    from uuid import uuid4
    from app.core import worker_context
    from app.repositories import job_repository
    from app.services.document_jobs import process_document_job

    stopping = Event()
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: stopping.set())
    worker_slot = f'{kind}:{slot}'
    namespace = {'transcription': 72815101, 'document': 72815102, 'visual': 72815103}[kind]
    with get_connection() as session:
        session.autocommit = True
        # Shared pool lock excludes the backwards-compatible standalone serial worker.
        while not stopping.is_set():
            shared = session.execute(
                'SELECT pg_try_advisory_lock_shared(%s) AS acquired', (WORKER_LOCK_ID,)
            ).fetchone()['acquired']
            if shared:
                break
            if not wait_for_lock:
                raise RuntimeError('A serial worker is running for this database.')
            stopping.wait(2)
        else:
            return
        while not stopping.is_set():
            if session.execute(
                'SELECT pg_try_advisory_lock(%s,%s) AS acquired', (namespace, slot)
            ).fetchone()['acquired']:
                break
            if not wait_for_lock:
                raise RuntimeError('This worker slot is already running.')
            stopping.wait(2)
        else:
            return
        with worker_context.bind(session, worker_slot, uuid4()):
            logger.info(
                'worker_slot_started slot=%s interrupted_jobs=%s',
                worker_slot,
                job_repository.recover(kind, worker_slot),
            )
            while not stopping.is_set():
                session.execute('SELECT 1')
                job = job_repository.claim(kind)
                if job:
                    if kind == 'transcription':
                        process_video_job(job)
                    elif kind == 'visual':
                        process_visual_job(
                            {
                                'job_id': job.job_id,
                                'file_id': job.file_id,
                                'storage_path': str(job.storage_path),
                                'duration_ms': job.duration_ms,
                            }
                        )
                    elif job.job_type == 'presentation_analysis':
                        process_presentation_job(job)
                    else:
                        process_document_job(job)
                elif not once:
                    stopping.wait(1)
                if once:
                    return


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
    parser = argparse.ArgumentParser(description='Process queued ReStore video transcription jobs.')
    parser.add_argument('--once', action='store_true', help='Process at most one queued job, then exit.')
    parser.add_argument(
        '--wait-for-lock',
        action='store_true',
        help='Wait for an existing worker to finish before claiming jobs.',
    )
    parser.add_argument('--kind', choices=['transcription', 'document', 'visual'])
    parser.add_argument('--slot', type=int, default=0)
    options = parser.parse_args()
    try:
        if options.kind:
            if not 0 <= options.slot < 8:
                raise ValueError('Slot must be between 0 and 7')
            run_slot_worker(options.kind, options.slot, options.once, options.wait_for_lock)
        else:
            run_worker(options.once, options.wait_for_lock)
    except Exception as exc:
        logger.error("worker_stopped error_type=%s", type(exc).__name__)
        raise SystemExit(1) from None
