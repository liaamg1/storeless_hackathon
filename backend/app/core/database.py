import psycopg
from psycopg.rows import dict_row

from app.core.config import get_settings


def get_connection() -> psycopg.Connection:
    """Open a connection; callers own its context and transaction lifetime."""
    return psycopg.connect(get_settings().database_url, row_factory=dict_row)
