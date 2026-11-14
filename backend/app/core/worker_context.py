"""A worker's writes use the same session that holds its ownership locks.

If that session is lost, the old process cannot commit results after a new owner
recovers its jobs. API requests continue to use independent short connections.
"""

from contextlib import contextmanager
from contextvars import ContextVar

connection = ContextVar('worker_connection', default=None)
owner = ContextVar('worker_owner', default=None)
slot = ContextVar('worker_slot', default=None)


@contextmanager
def bind(session, worker_slot, worker_id):
    tokens = connection.set(session), slot.set(worker_slot), owner.set(worker_id)
    try:
        yield
    finally:
        connection.reset(tokens[0])
        slot.reset(tokens[1])
        owner.reset(tokens[2])


@contextmanager
def transaction(session):
    with session.transaction():
        yield session
