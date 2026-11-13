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
                "SELECT pg_try_advisory_lock(%s) AS acquired", (WORKER_LOCK_ID,),
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
                        elif not once:
                            stopping.wait(2)
                if once:
                    return
            except Exception as exc:
                logger.error("worker_database_failure error_type=%s", type(exc).__name__)
                # Exit instead of continuing without the exclusivity guarantee.
                raise RuntimeError("Worker stopped after a database failure; restart it to recover jobs.") from None


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
    parser = argparse.ArgumentParser(description='Process queued ReStore video transcription jobs.')
    parser.add_argument('--once', action='store_true', help='Process at most one queued job, then exit.')
    parser.add_argument('--wait-for-lock', action='store_true', help='Wait for an existing worker to finish before claiming jobs.')
    options = parser.parse_args()
    try:
        run_worker(options.once, options.wait_for_lock)
    except Exception as exc:
        logger.error("worker_stopped error_type=%s", type(exc).__name__)
        raise SystemExit(1) from None
