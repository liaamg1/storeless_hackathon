import psycopg
from psycopg.rows import dict_row

from app.core.config import get_settings


def new_connection() -> psycopg.Connection:
    """Open an independent connection, including for committed progress updates."""
    return psycopg.connect(get_settings().database_url, row_factory=dict_row)


def get_connection():
    from app.core import worker_context

    session = worker_context.connection.get()
    return worker_context.transaction(session) if session is not None else new_connection()
