"""환경변수 설정. 시크릿은 코드에 두지 않는다 (CLAUDE.md 4절)."""

from datetime import timedelta

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AXLINK_", env_file=".env", extra="ignore")

    # 호스트 노출 포트는 15432 다 (infra/docker-compose.yml — 로컬 PG 충돌 회피).
    database_url: str = "postgresql://axlink:axlink@localhost:15432/axlink"
    db_pool_min: int = 1
    db_pool_max: int = 10

    # 개발 기본값이다. 운영에서는 AXLINK_JWT_SECRET 을 반드시 주입한다.
    jwt_secret: str = "dev-only-change-me-in-production-please-32bytes"
    jwt_issuer: str = "ax-link"
    access_ttl_seconds: int = 30 * 60
    refresh_ttl_days: int = 14

    cors_origins: str = "http://localhost:5173"

    # 인증정보 암호화 마스터 키(base64 32바이트). 없으면 일회용 키를 만들어 쓰되,
    # 재기동하면 기존 암호문을 못 푼다 — 운영에서는 AXLINK_SECRET_KEY 를 반드시 준다.
    secret_key: str = ""

    # 커넥터가 원천 도구 REST 를 부를 때의 타임아웃(초)
    connector_timeout: float = 10.0

    @property
    def access_ttl(self) -> timedelta:
        return timedelta(seconds=self.access_ttl_seconds)

    @property
    def refresh_ttl(self) -> timedelta:
        return timedelta(days=self.refresh_ttl_days)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
