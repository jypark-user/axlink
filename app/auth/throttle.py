"""로그인 연속 실패 제한 (보안대책 5절 R1).

같은 아이디로 연속 실패가 문턱을 넘으면 잠시 로그인을 받지 않는다. 비밀번호 대입을 늦추는
것이 목적이다. 성공하면 그 아이디의 실패 기록을 지운다.

기록은 API 프로세스 메모리에 둔다. 운영 구성에서 API 는 한 프로세스이고(스케줄러도 같은
프로세스), 재시작하면 기록이 사라지는 것은 받아들인다. 접속지(IP)는 보지 않는다. 앞단
프록시 뒤라 IP 를 믿을 수 없고, 아이디 단위로 막으면 대입은 같은 효과로 늦어진다.

bcrypt 가 맞는 비밀번호를 가끔 거부하는 환경(Python 3.13, DEF-V042)이 있어 문턱을 넉넉히 둔다.
"""

import threading
import time

MAX_FAILURES = 10
WINDOW_SECONDS = 10 * 60  # 이 시간 안의 실패만 센다
LOCK_SECONDS = 10 * 60

_lock = threading.Lock()
_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


def _key(username: str) -> str:
    return username.strip().lower()


def locked_for(username: str, now: float | None = None) -> int:
    """잠겨 있으면 남은 초, 아니면 0."""
    now = time.monotonic() if now is None else now
    with _lock:
        until = _locked_until.get(_key(username), 0.0)
        if until <= now:
            _locked_until.pop(_key(username), None)
            return 0
        return int(until - now) + 1


def fail(username: str, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    key = _key(username)
    with _lock:
        recent = [t for t in _failures.get(key, []) if now - t < WINDOW_SECONDS]
        recent.append(now)
        if len(recent) >= MAX_FAILURES:
            _locked_until[key] = now + LOCK_SECONDS
            recent = []
        _failures[key] = recent


def succeed(username: str) -> None:
    key = _key(username)
    with _lock:
        _failures.pop(key, None)
        _locked_until.pop(key, None)


def reset() -> None:
    """시험용. 관리자 비밀번호 재설정 뒤에도 부른다."""
    with _lock:
        _failures.clear()
        _locked_until.clear()
