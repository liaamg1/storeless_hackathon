"""Own the local worker for the lifetime of the API, outside request handling."""

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from app.core.config import BACKEND_DIR, get_worker_settings

logger = logging.getLogger(__name__)
SHUTDOWN_TIMEOUT_SECONDS = 10


async def wait_for_stop(stopping: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stopping.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def stop_worker(process: asyncio.subprocess.Process) -> None:
    """Finish the current job if possible; bounded shutdown also works with reload."""
    if process.returncode is not None:
        return
    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=SHUTDOWN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("transcription_worker_shutdown_timeout pid=%s", process.pid)
        # The worker owns its session, so stop FFmpeg descendants as well if forced.
        try:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass  # It exited between the timeout and the kill request.
        await process.wait()
    except ProcessLookupError:
        await process.wait()


async def supervise_worker(stopping: asyncio.Event, kind: str | None = None, slot: int = 0) -> None:
    """Restart a crashed worker; PostgreSQL keeps queued work and recovery state."""
    while not stopping.is_set():
        try:
            arguments = [sys.executable, '-m', 'app.worker', '--wait-for-lock']
            kwargs = {'cwd': str(BACKEND_DIR), 'start_new_session': True}
            if kind is not None:
                arguments += ['--kind', kind, '--slot', str(slot)]
                env = os.environ.copy()
                # Keep NumPy/BLAS/FFmpeg work from creating a thread pool per process.
                threads = env.get('WHISPER_CPU_THREADS', '3') if kind == 'transcription' else '1'
                for variable in (
                    'OMP_NUM_THREADS',
                    'OPENBLAS_NUM_THREADS',
                    'MKL_NUM_THREADS',
                    'NUMEXPR_NUM_THREADS',
                ):
                    env[variable] = threads
                kwargs['env'] = env
            process = await asyncio.create_subprocess_exec(*arguments, **kwargs)
        except OSError as exc:
            logger.error("transcription_worker_start_failed error_type=%s", type(exc).__name__)
            await wait_for_stop(stopping, 2)
            continue
        logger.info("transcription_worker_started pid=%s", process.pid)
        try:
            while process.returncode is None and not stopping.is_set():
                await wait_for_stop(stopping, 1)
            if not stopping.is_set():
                logger.error("transcription_worker_exited return_code=%s restarting=true", process.returncode)
        finally:
            await stop_worker(process)
        if not stopping.is_set():
            await wait_for_stop(stopping, 2)


@asynccontextmanager
async def manage_transcription_worker() -> AsyncIterator[None]:
    """Start automatically for the demo; standalone deployments can opt out."""
    enabled = os.getenv('AUTO_START_TRANSCRIPTION_WORKER', 'true').strip().lower()
    if enabled in {'0', 'false', 'no', 'off'}:
        logger.info('transcription_worker_autostart_disabled')
        yield
        return
    stopping = asyncio.Event()
    settings = get_worker_settings()
    supervisors = [
        asyncio.create_task(supervise_worker(stopping, kind, slot), name=f'{kind}-{slot}-supervisor')
        for kind, count in [
            ('transcription', settings.transcription),
            ('document', settings.document),
            ('visual', settings.visual),
        ]
        for slot in range(count)
    ]
    try:
        yield
    finally:
        stopping.set()
        await asyncio.gather(*supervisors)
