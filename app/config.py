"""환경변수 설정. 시크릿은 코드에 두지 않는다 (작업 규약 §4)."""

from datetime import timedelta

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-change-me-in-production-please-32bytes"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AXLINK_", env_file=".env", extra="ignore")

    # 호스트 노출 포트는 15432 다 (infra/docker-compose.yml — 로컬 PG 충돌 회피).
    database_url: str = "postgresql://axlink:axlink@localhost:15432/axlink"
    db_pool_min: int = 1
    db_pool_max: int = 10

    # 실행 환경(AXLINK_ENV). production 이면 아래 비밀값이 기본값이거나 비어 있을 때
    # 기동하지 않는다.
    env: str = "development"

    # 개발 기본값이다. 운영에서는 AXLINK_JWT_SECRET 을 반드시 주입한다.
    jwt_secret: str = DEV_JWT_SECRET
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
    llm_provider: str = "ollama"          # ollama | fake
    # 1단계 경량 검증용 잠정값. 모델 확정은 로컬 검증(작업 규약 §5) 결과로 한다.
    llm_model: str = "qwen3:4b"
    llm_timeout: float = 120.0
    scheduler_enabled: bool = True  # 서버 안 스케줄러(일별 스냅샷·주기 수집). 시험에서 끈다
    # 생성 문맥 길이. 근거 청크 5개(각 최대 1000토큰)와 지시가 들어가야 한다.
    llm_num_ctx: int = 8192
    # 생성 모델 서버의 기본 주소. 관리 화면에서 고른 주소(DB llm_setting)가 있으면 그쪽이 이긴다.
    ollama_base_url: str = "http://localhost:11434"
    # 임베딩 서버 주소. 비우면 ollama_base_url 을 쓴다. 생성은 클라우드 모델을 거치고 임베딩은
    # 로컬 bge-m3 로 두는 구성처럼 두 서버가 다를 때 따로 준다.
    embedding_base_url: str = ""
    embedding_model: str = "bge-m3"
    embedding_dimension: int = 1024  # doc_chunk.embedding 컬럼 차원과 반드시 같아야 한다
    embedding_batch: int = 32
    embedding_timeout: float = 120.0  # 배치 임베딩은 커넥터 호출보다 오래 걸린다

    # 배포 버전. 이미지가 빌드 때 넣고 /api/health 가 돌려준다. 호스트 실행은 dev 다.
    app_version: str = "dev"

    # 저장소에서 함께 수집할 산출물 파일. "경로=산출물유형" 을 쉼표로 잇는다.
    # WBS 는 도구가 아니라 커밋된 파일로 관리하므로(작업 규약 §2) 여기를 거쳐 들어온다.
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

    # AI 질의 검색과 근거 게이트 (ARC-010)
    rag_candidates: int = 20  # 벡터·어휘 검색이 각각 내는 후보 수
    rag_top_k: int = 5  # 프롬프트에 넣는 근거 청크 수
    rag_rrf_k: int = 60  # RRF 상수. 순위 융합에서 1위와 2위의 차이를 완만하게 한다
    # 최고 코사인 유사도가 이 값 미만이면 LLM 을 부르지 않고 "근거 부족"으로 답한다.
    # 09.14 실측(bge-m3, 저장소 문서 5건): 답이 있는 질문은 0.55~0.68, 관계없는 질문은
    # 0.38~0.51 이었다. 08.31 실측의 정답 1순위는 0.719. 근거는 ARC-010.
    rag_min_similarity: float = 0.55
    rag_snippet_chars: int = 300
    # 목록 질문("이슈 목록", "요구사항 뭐가 있어")은 어떤 청크 내용과도 닮지 않아 유사도로는
    # 못 찾는다(09.15 실측: 이슈 청크 안에서도 0.38, 무관 질문은 0.47). 종류로 골라 소스당
    # 한 청크씩 앞부분만 넣는다. 41건 × 160자 ≈ 3천 토큰이라 8192 문맥에 든다.
    rag_list_limit: int = 60
    rag_list_chars: int = 160
    # 라우팅 캐시(ARC-014). 같은 질문의 판정을 모델에 다시 묻지 않는다. 값은 매번 새로 뽑는다.
    rag_route_cache: bool = True
    # 실행 중인 코드의 이름표. 미리보기·배포를 띄울 때 넣는다. 질의 화면에 모델과 같이 보인다
    build_label: str | None = None
    # 일반 질문 답변율의 바닥. live 시험이 이 아래면 실패한다. 기준선을 잰 뒤 올린다.
    rag_general_answer_floor: float = 0.85  # 09.17 실측 100%. 판정이 흔들려 여유를 둔다

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

    def production_problems(self) -> list[str]:
        """운영에서 빠지면 안 되는 비밀값 중 빠진 것. 개발 환경이면 늘 빈 목록이다."""
        if self.env != "production":
            return []
        problems = []
        if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("AXLINK_JWT_SECRET 이 개발 기본값이거나 32자보다 짧다")
        if not self.secret_key:
            problems.append("AXLINK_SECRET_KEY 가 없다 (저장된 도구 인증정보를 풀 수 없게 된다)")
        return problems

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
