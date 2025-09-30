from contextlib import contextmanager
import psycopg2
import psycopg2.pool
from . import config


POOL = None


def init_db_pool():
    global POOL
    if POOL is not None:
        return POOL
    if config.DATABASE_URL:
        dsn = config.DATABASE_URL
    else:
        dsn = f"host={config.PG_HOST} port={config.PG_PORT} dbname={config.PG_DB} user={config.PG_USER} password={config.PG_PASSWORD}"
    POOL = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)
    return POOL


@contextmanager
def get_conn():
    conn = POOL.getconn()
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        POOL.putconn(conn)

