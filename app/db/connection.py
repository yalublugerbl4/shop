import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from app.config import settings
from typing import Generator


@contextmanager
def get_db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Контекстный менеджер для подключения к БД"""
    conn = psycopg2.connect(
        settings.database_url,
        cursor_factory=RealDictCursor
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db_cursor():
    """Получить курсор БД"""
    return get_db_connection()

