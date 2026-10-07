# AX Link 웹 이미지. 빌드 문맥은 저장소 루트다.
#
#   docker build -f docker/web.Dockerfile --target prod \
#     --build-arg AXLINK_VERSION=0.1.0 --build-arg AXLINK_REVISION=$(git rev-parse --short HEAD) \
#     -t axlink-web:0.1.0 .
#
# dev 단계는 Vite 개발 서버다(infra/docker-compose.yml). prod 단계는 빌드 결과를 Nginx 로 낸다.

FROM node:24-bookworm-slim AS deps
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

# ── 개발용: 소스를 이미지에 넣고, 고친 파일은 `docker compose watch` 가 컨테이너로 옮긴다 ──
# Windows 폴더를 바인드 마운트해 polling 으로 감시하면 도커의 D: 공유(9p)가 끊겼다(10-01 실측).
# 컨테이너 안 파일이라 Vite 가 보통의 파일 알림으로 바로 반영한다.
# 호스트(Windows)의 node_modules 는 쓰지 않는다. 플랫폼별 바이너리(esbuild·rollup)가 다르다.
FROM deps AS dev
COPY docker/web-dev-entrypoint.sh /usr/local/bin/web-dev-entrypoint
COPY frontend/ ./
RUN chmod +x /usr/local/bin/web-dev-entrypoint \
 && sha256sum package-lock.json | cut -d' ' -f1 > node_modules/.lock-hash
EXPOSE 5173
ENTRYPOINT ["web-dev-entrypoint"]
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]

FROM deps AS build
ARG AXLINK_VERSION=dev
ARG AXLINK_REVISION=unknown
# 앱이 놓일 경로. 외부 공개(/ax-link/)는 빌드 때 정해진다. 기동 때의 AXLINK_BASE_PATH 와 같아야 한다
ARG AXLINK_BASE_PATH=/
ENV AXLINK_BASE_PATH=${AXLINK_BASE_PATH}
COPY frontend/ ./
RUN npm run build \
 && printf '{"name":"axlink-web","version":"%s","revision":"%s"}\n' \
      "${AXLINK_VERSION}" "${AXLINK_REVISION}" > dist/version.json

# ── 운영용 ──
FROM nginxinc/nginx-unprivileged:1.27-alpine AS prod
ARG AXLINK_VERSION=dev
ARG AXLINK_REVISION=unknown
LABEL org.opencontainers.image.title="axlink-web" \
      org.opencontainers.image.version="${AXLINK_VERSION}" \
      org.opencontainers.image.revision="${AXLINK_REVISION}" \
      org.opencontainers.image.source="https://github.com/jypark-user/axlink"
# 설정은 기동 때 docker/nginx/40-axlink-site.sh 가 만든다(API 주소·앱 경로·받을 호스트).
ARG AXLINK_BASE_PATH=/
ENV AXLINK_API_UPSTREAM=http://api:8080 \
    AXLINK_BASE_PATH=${AXLINK_BASE_PATH} \
    AXLINK_SERVER_NAMES="" \
    AXLINK_LOCAL_NAMES=""
COPY --chmod=0755 docker/nginx/40-axlink-site.sh /docker-entrypoint.d/40-axlink-site.sh
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/version.json || exit 1
