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

    # AI 포트 구현체 선택 단일 지점. ollama | fake
    # fake 는 결정적 벡터를 만들어 모델 없이도 테스트가 돌게 한다.
    embedding_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    embedding_dimension: int = 1024  # doc_chunk.embedding 컬럼 차원과 반드시 같아야 한다
    embedding_batch: int = 32
    embedding_timeout: float = 120.0  # 배치 임베딩은 커넥터 호출보다 오래 걸린다

    # 저장소에서 함께 수집할 산출물 파일. "경로=산출물유형" 을 쉼표로 잇는다.
    # WBS 는 도구가 아니라 커밋된 파일로 관리하므로(CLAUDE.md 2절) 여기를 거쳐 들어온다.
    collect_files: str = "docs/00-management/WBS.xlsx=PROJECT_PLAN"
    # 파일을 읽을 브랜치. 비우면 저장소 기본 브랜치를 본다.
    collect_ref: str = ""

    # 업로드 문서 원본 보관 위치. 폐쇄망 온프레미스라 오브젝트 스토리지를 전제하지 않는다.
    # 운영에서는 NAS 마운트 경로를 AXLINK_DOCUMENT_ROOT 로 준다.
    document_root: str = "var/documents"

    # 청킹 파라미터 (파일럿 설계 03-physical-backend §6.1)
    chunk_target_tokens: int = 800
    chunk_min_tokens: int = 200
    chunk_max_tokens: int = 1000
    chunk_overlap_ratio: float = 0.15

    @property
    def access_ttl(self) -> timedelta:
        return timedelta(seconds=self.access_ttl_seconds)

    @property
    def refresh_ttl(self) -> timedelta:
        return timedelta(days=self.refresh_ttl_days)

    @property
    def collect_file_map(self) -> dict[str, str]:
        """{저장소 경로: 산출물 유형}. 빈 설정이면 파일을 수집하지 않는다."""
        pairs = (item.split("=", 1) for item in self.collect_files.split(",") if "=" in item)
        return {path.strip(): kind.strip() for path, kind in pairs if path.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
