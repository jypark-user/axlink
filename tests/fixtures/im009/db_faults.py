"""시험 DB 저장 실패 주입 (IM-007 UC-021-S06·UC-032-S07).

한 흐름의 뒤쪽 단계 테이블에 「이 행이면 예외」 트리거를 걸어, 앞 단계가 이미 쓴 뒤에 저장이
실패하게 만든다. 그 흐름이 한 트랜잭션으로 되돌아가는지(아무것도 안 바뀌는지) 본다.

원격 대상(5174)에서도 트리거는 그 서버가 쓰는 시험 DB 에 걸린다(AXLINK_DATABASE_URL). 이름이
`axlink_test` 로 끝나지 않는 DB 에서는 걸지 않고 시험을 건너뛴다. 운영·개발 DB 보호 장치다.
트리거·함수 이름은 `im009_test_fault_` 로 시작하고, 끝나면(실패해도) 지운다.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest

from app.db import fetch_one, tx

PREFIX = "im009_test_fault_"
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _require_test_db() -> str:
    with tx() as cur:
        name = fetch_one(cur, "select current_database() as d")["d"]
    if not name.endswith("axlink_test"):
        pytest.skip(f"저장 실패 주입은 시험 DB(이름 …axlink_test)에서만 한다. 지금 DB: {name}")
    return name


@contextmanager
def fail_insert(table: str, column: str, value: str, tag: str) -> Iterator[None]:
    """`table` 에 `column` = `value`(UUID) 인 행이 들어오면 예외를 던진다. 블록이 끝나면 지운다."""
    for ident in (table, column, tag):
        if not _IDENT.match(ident):
            raise ValueError(f"식별자가 아니다: {ident!r}")
    marker = str(uuid.UUID(value))  # UUID 만 받는다. 문자열을 SQL 에 그대로 넣지 않는다
    _require_test_db()
    name = PREFIX + tag
    with tx() as cur:
        cur.execute(
            f"""
            create or replace function {name}() returns trigger language plpgsql as $f$
            begin
              if NEW.{column}::text = '{marker}' then
                raise exception 'IM-009 시험 저장 실패 주입({tag})';
              end if;
              return NEW;
            end
            $f$
            """
        )
        cur.execute(f"drop trigger if exists {name} on {table}")
        cur.execute(
            f"create trigger {name} before insert on {table} "
            f"for each row execute function {name}()"
        )
    try:
        yield
    finally:
        with tx() as cur:
            cur.execute(f"drop trigger if exists {name} on {table}")
            cur.execute(f"drop function if exists {name}()")


def rejected(call: Callable[[], object]) -> str:
    """주입한 실패 아래서 요청을 보낸다. 실패면 응답(또는 오류) 문장, 성공이면 빈 문자열.

    원격 서버는 500 응답을 준다. 프로세스 안 TestClient 는 서버 예외를 그대로 올리므로 그 예외를
    주입한 실패로 확인하고 받는다."""
    try:
        res = call()
    except Exception as exc:  # noqa: BLE001 — TestClient 가 올린 서버 예외
        if "저장 실패 주입" not in str(exc):
            raise
        return str(exc)[:200]
    status = getattr(res, "status_code", 200)
    return f"{status} {getattr(res, 'text', '')[:200]}" if status >= 400 else ""
