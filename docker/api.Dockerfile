# AX Link API 이미지. 빌드 문맥은 저장소 루트다.
#
#   docker build -f docker/api.Dockerfile --target prod \
#     --build-arg AXLINK_VERSION=0.1.0 --build-arg AXLINK_REVISION=$(git rev-parse --short HEAD) \
#     -t axlink-api:0.1.0 .
#
# dev 단계는 소스를 붙여 쓰는 개발용이다(infra/docker-compose.yml). prod 단계는 소스 마운트 없이 돈다.

FROM python:3.12-slim AS deps
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /build
COPY pyproject.toml ./
# 의존성만 먼저 깐다. 소스가 바뀌어도 이 층은 다시 받지 않는다.
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
open('requirements.txt', 'w').write('\n'.join(d['dependencies']))" \
 && pip install -r requirements.txt

# ── 개발용: 소스를 이미지에 넣고, 고친 파일은 `docker compose watch` 가 컨테이너로 옮긴다 ──
# Windows 폴더를 붙여 쓰면 도커의 D: 공유(9p)가 끊길 때 API 가 I/O 오류를 냈다(10-01).
# 호스트의 .venv·.env·.git·var 는 컨테이너에 들어가지 않는다.
FROM deps AS dev
# 규약 시험(tests/test_traceability.py)이 커밋 이력을 읽는다. 붙인 저장소는 소유자가 달라 안전 경로로 둔다
RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory /app
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
open('requirements-dev.txt', 'w').write('\n'.join(d['optional-dependencies']['dev']))" \
 && pip install -r requirements-dev.txt
WORKDIR /app
COPY app ./app
# 업로드 문서는 이름 있는 볼륨에 둔다(infra/docker-compose.yml). 운영과 같은 경로다
ENV AXLINK_DOCUMENT_ROOT=/data/documents
RUN mkdir -p /data/documents
EXPOSE 8080
# 스케줄러가 앱 안에 있어 worker 는 하나다. --reload 는 감시 프로세스와 worker 한 개로 돈다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload", "--reload-dir", "app"]

# ── 운영용 ──
FROM deps AS build
COPY app ./app
RUN pip install --no-deps .

FROM python:3.12-slim AS prod
ARG AXLINK_VERSION=dev
ARG AXLINK_REVISION=unknown
LABEL org.opencontainers.image.title="axlink-api" \
      org.opencontainers.image.version="${AXLINK_VERSION}" \
      org.opencontainers.image.revision="${AXLINK_REVISION}" \
      org.opencontainers.image.source="https://github.com/jypark-user/axlink"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    AXLINK_APP_VERSION="${AXLINK_VERSION}+${AXLINK_REVISION}" \
    AXLINK_DOCUMENT_ROOT=/data/documents \
    AXLINK_MANUAL_DIR=/srv/axlink/docs/40-manual
COPY --from=build /opt/venv /opt/venv
# 화면이 /api/help 로 보여 주는 사용 안내 문서(원천은 docs/40-manual)
COPY docs/40-manual /srv/axlink/docs/40-manual
# 업로드 문서 보관 위치. 빈 볼륨을 처음 붙이면 이 소유권이 볼륨으로 옮겨진다.
RUN useradd --system --uid 10001 --home-dir /srv/axlink axlink \
 && mkdir -p /srv/axlink /data/documents \
 && chown -R axlink:axlink /srv/axlink /data/documents
WORKDIR /srv/axlink
USER axlink
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4)"
# 스케줄러가 앱 안에 있어 컨테이너 하나, worker 하나로 돈다. 늘리면 스냅샷·수집이 겹친다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
