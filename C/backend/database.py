import logging
from typing import Any

import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL, MAX_RETURN_ROWS, SQL_QUERY_TIMEOUT

logger = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_raw_query(sql: str, params: dict | tuple | None = None) -> list[dict[str, Any]]:
    result = []
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SET statement_timeout = '{SQL_QUERY_TIMEOUT}s'")
            if params is not None:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            rows = cur.fetchmany(MAX_RETURN_ROWS)
            if rows:
                for row in rows:
                    result.append(dict(row))

        return result

    except Exception as e:
        logger.error(f"Raw query execution failed: {e}")
        raise
    finally:
        if conn:
            conn.close()
