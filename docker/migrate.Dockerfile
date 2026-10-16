# AX Link 스키마 마이그레이션 이미지. 운영에서는 db/migration 을 마운트하지 않고 이 이미지에 담아 간다.
#
#   docker build -f docker/migrate.Dockerfile \
#     --build-arg AXLINK_VERSION=0.1.0 --build-arg AXLINK_REVISION=$(git rev-parse --short HEAD) \
#     -t axlink-migrate:0.1.0 .
#
# 접속 정보는 FLYWAY_URL·FLYWAY_USER·FLYWAY_PASSWORD 환경변수로 준다. 기본 명령은 migrate 다.
# migrate 는 적용 전에 validate(체크섬·누락 이력 확인)를 먼저 돈다.

# PostgreSQL JDBC 드라이버. Flyway 는 /flyway/drivers 에 둔 드라이버를 쓴다(공식 지원 경로).
# 같은 42.7 줄의 최신 패치로 바꾼다(CVE-2026-42198, 42.7.2 → 42.7.11 이상). Maven Central 의
# sha1 과 대조한 sha256 으로 고정한다. 판을 올릴 때 두 값을 같이 바꾼다.
FROM curlimages/curl:8.11.1 AS pgjdbc
ARG PGJDBC_VERSION=42.7.14
ARG PGJDBC_SHA256=73914527305a40cce504b0d3d90b23caf565136912d607ae8ae7c5895512332c
RUN curl -fsSL -o /tmp/postgresql-${PGJDBC_VERSION}.jar \
      "https://repo1.maven.org/maven2/org/postgresql/postgresql/${PGJDBC_VERSION}/postgresql-${PGJDBC_VERSION}.jar" \
 && echo "${PGJDBC_SHA256}  /tmp/postgresql-${PGJDBC_VERSION}.jar" | sha256sum -c -

FROM flyway/flyway:10
ARG AXLINK_VERSION=dev
ARG AXLINK_REVISION=unknown
ARG PGJDBC_VERSION=42.7.14
LABEL org.opencontainers.image.title="axlink-migrate" \
      org.opencontainers.image.version="${AXLINK_VERSION}" \
      org.opencontainers.image.revision="${AXLINK_REVISION}" \
      org.opencontainers.image.source="https://github.com/jypark-user/axlink"
# flyway:10 은 2024-11 이후 다시 만들어지지 않는다. 쓰지 않는 다른 DB 드라이버(Cassandra 의 netty
# CVE-2026-75595 등)와 함께 들어 있던 PostgreSQL 드라이버도 빼고 위에서 받은 것만 둔다.
# OS 는 걸린 패키지만 보안 갱신한다(ARC-026 4-4)
RUN rm -rf /flyway/drivers/* \
 && apt-get update \
 && apt-get install -y --no-install-recommends --only-upgrade \
      openssl libssl3 gpgv gnupg gpg gpg-agent gpgsm gpgconf dirmngr gnupg-utils \
      gpg-wks-client gpg-wks-server gnupg-l10n \
 && rm -rf /var/lib/apt/lists/*
COPY --from=pgjdbc /tmp/postgresql-${PGJDBC_VERSION}.jar /flyway/drivers/
ENV FLYWAY_LOCATIONS=filesystem:/flyway/sql \
    FLYWAY_CONNECT_RETRIES=20
COPY db/migration/ /flyway/sql/
CMD ["migrate"]
