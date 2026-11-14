"""Compatibility for callers expecting extracted pages in the legacy HTTP reply."""

from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from threading import Lock
from app.core.config import get_worker_settings

_pool = None
_lock = Lock()


def extract_in_process(extractor, path):
    global _pool
    with _lock:
        if _pool is None:
            _pool = ProcessPoolExecutor(
                max_workers=get_worker_settings().document, mp_context=get_context('spawn')
            )
        pool = _pool
    return pool.submit(extractor, path).result()


def shutdown():
    global _pool
    with _lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=True, cancel_futures=True)
