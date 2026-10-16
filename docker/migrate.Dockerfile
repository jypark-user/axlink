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
# flyway:10 은 2024-11 이후 다시 만들어지지 않는다. 쓰지 않는 다른 DB 드라이버(Cassandra 의 netty
# CVE-2026-75595 등)를 빼고 PostgreSQL 드라이버만 둔다. OS 는 걸린 패키지만 보안 갱신한다(ARC-026 4-4)
RUN find /flyway/drivers -mindepth 1 -maxdepth 1 ! -name 'postgresql-*.jar' -exec rm -rf {} + \
 && apt-get update \
 && apt-get install -y --no-install-recommends --only-upgrade \
      openssl libssl3 gpgv gnupg gpg gpg-agent gpgsm gpgconf dirmngr gnupg-utils \
      gpg-wks-client gpg-wks-server gnupg-l10n \
 && rm -rf /var/lib/apt/lists/*
ENV FLYWAY_LOCATIONS=filesystem:/flyway/sql \
    FLYWAY_CONNECT_RETRIES=20
COPY db/migration/ /flyway/sql/
CMD ["migrate"]
