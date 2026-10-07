# AX Link 스키마 마이그레이션 이미지. 운영에서는 db/migration 을 마운트하지 않고 이 이미지에 담아 간다.
#
#   docker build -f docker/migrate.Dockerfile \
#     --build-arg AXLINK_VERSION=0.1.0 --build-arg AXLINK_REVISION=$(git rev-parse --short HEAD) \
#     -t axlink-migrate:0.1.0 .
#
# 접속 정보는 FLYWAY_URL·FLYWAY_USER·FLYWAY_PASSWORD 환경변수로 준다. 기본 명령은 migrate 다.
# migrate 는 적용 전에 validate(체크섬·누락 이력 확인)를 먼저 돈다.

FROM flyway/flyway:10
ARG AXLINK_VERSION=dev
ARG AXLINK_REVISION=unknown
LABEL org.opencontainers.image.title="axlink-migrate" \
      org.opencontainers.image.version="${AXLINK_VERSION}" \
      org.opencontainers.image.revision="${AXLINK_REVISION}" \
      org.opencontainers.image.source="https://github.com/jypark-user/axlink"
ENV FLYWAY_LOCATIONS=filesystem:/flyway/sql \
    FLYWAY_CONNECT_RETRIES=20
COPY db/migration/ /flyway/sql/
CMD ["migrate"]
