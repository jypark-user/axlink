"""psycopg 3 커넥션 풀. ORM 을 쓰지 않으므로 SQL 은 각 repository 가 직접 쓴다.

ORM 금지 사유는 작업 규약 §1에 있다 — 시맨틱 레이어가 카탈로그 조각으로 SQL 을
조립하는 것이 본질이고, vector(1024)·tsvector·부분 유니크 on conflict 가 네이티브 SQL 을
요구한다. 언어가 바뀌어도 같은 이유다.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.database_url,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def tx() -> Iterator[Any]:
    """트랜잭션 하나를 열고 커서를 넘긴다. 예외가 나면 롤백된다."""
    with pool().connection() as conn, conn.cursor() as cur:
        yield cur


def fetch_all(cur: Any, sql: str, params: Any = None) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return cur.fetchall()


def fetch_one(cur: Any, sql: str, params: Any = None) -> dict[str, Any] | None:
    cur.execute(sql, params)
    return cur.fetchone()
