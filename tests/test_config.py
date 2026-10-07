"""운영 설정 검사. 값은 실제 환경변수 이름(AXLINK_*)으로 넣어 본다.

필드 이름과 환경변수 이름이 어긋나면 Settings(env="production") 처럼 직접 넣는 시험은
통과해도 운영 컴포즈가 준 값은 읽히지 않는다(10-01, AXLINK_ENV 가 environment 필드에
닿지 않아 운영 검사가 꺼져 있었다). 그래서 여기서는 환경변수로만 넣는다.
"""

import pytest

from app.config import DEV_JWT_SECRET, Settings

GOOD_JWT = "x" * 48
GOOD_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _settings(monkeypatch, **env: str) -> Settings:
    for name in ("AXLINK_ENV", "AXLINK_JWT_SECRET", "AXLINK_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_AXLINK_ENV_가_실행_환경으로_읽힌다(monkeypatch):
    assert _settings(monkeypatch, AXLINK_ENV="production").env == "production"
    assert _settings(monkeypatch).env == "development"


def test_개발_환경은_비밀값이_없어도_막지_않는다(monkeypatch):
    assert _settings(monkeypatch, AXLINK_ENV="development").production_problems() == []


@pytest.mark.parametrize(
    ("jwt", "key", "expect"),
    [
        (DEV_JWT_SECRET, GOOD_KEY, ["AXLINK_JWT_SECRET"]),
        ("short-secret", GOOD_KEY, ["AXLINK_JWT_SECRET"]),
        (GOOD_JWT, "", ["AXLINK_SECRET_KEY"]),
        (GOOD_JWT, GOOD_KEY, []),
    ],
    ids=["기본_JWT", "짧은_JWT", "암호화_키_없음", "정상"],
)
def test_운영에서_빠진_비밀값을_찾는다(monkeypatch, jwt, key, expect):
    env = {"AXLINK_ENV": "production", "AXLINK_JWT_SECRET": jwt}
    if key:
        env["AXLINK_SECRET_KEY"] = key
    problems = _settings(monkeypatch, **env).production_problems()
    assert [p.split(" ")[0] for p in problems] == expect
