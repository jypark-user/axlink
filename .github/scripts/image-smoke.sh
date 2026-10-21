#!/usr/bin/env bash
# 이미지 기동 검증. 실행 PC 가 아니라 GitHub 러너에서 돈다(.github/workflows/image-build.yml).
#
#   image-smoke.sh <migrate 이미지> <api 이미지> <web 이미지> <기대 버전>
#
# 빈 시험 DB 에 마이그레이션 → 운영 모드 API 기동 → 웹(/ax-link/) 기동 순서로 올리고, 화면이 실제로
# 부르는 JS·CSS 와 API 프록시까지 확인한다. 비밀값은 이 실행에서만 만들고 출력하지 않는다.
set -euo pipefail

MIGRATE="$1" API="$2" WEB="$3" VERSION="$4"
NET=axlink-smoke
DB_URL=postgresql://axlink:axlink@db:5432/axlink
fail() { echo "::error::$*"; exit 1; }

cleanup() {
  docker logs smoke-api > smoke-api.log 2>&1 || true
  docker logs smoke-web > smoke-web.log 2>&1 || true
  docker rm -f smoke-db smoke-api smoke-web >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$NET" >/dev/null
docker run -d --name smoke-db --network "$NET" --network-alias db \
  -e POSTGRES_USER=axlink -e POSTGRES_PASSWORD=axlink -e POSTGRES_DB=axlink \
  --tmpfs /var/lib/postgresql/data pgvector/pgvector:pg16 >/dev/null
for _ in $(seq 1 60); do
  docker exec smoke-db pg_isready -U axlink -d axlink >/dev/null 2>&1 && break
  sleep 1
done

echo "== 마이그레이션"
docker run --rm --network "$NET" \
  -e FLYWAY_URL=jdbc:postgresql://db:5432/axlink -e FLYWAY_USER=axlink -e FLYWAY_PASSWORD=axlink \
  "$MIGRATE" migrate
expected=$(find db/migration -name 'V*__*.sql' | sed -E 's#.*/V([0-9]+)__.*#\1#' | sort -n | tail -1)
applied=$(docker exec smoke-db psql -U axlink -d axlink -Atc \
  "select max(version::int) from flyway_schema_history where success")
[ "$applied" = "$expected" ] || fail "마이그레이션 V$applied, 저장소 최신 V$expected"
echo "V$applied 까지 적용"

echo "== API (운영 모드)"
jwt=$(openssl rand -hex 32)
key=$(openssl rand -base64 32)
docker run -d --name smoke-api --network "$NET" --network-alias api -p 127.0.0.1:18080:8080 \
  -e AXLINK_ENV=production -e AXLINK_JWT_SECRET="$jwt" -e AXLINK_SECRET_KEY="$key" \
  -e AXLINK_DATABASE_URL="$DB_URL" -e AXLINK_EMBEDDING_PROVIDER=fake \
  -e AXLINK_SCHEDULER_ENABLED=false "$API" >/dev/null
unset jwt key
for _ in $(seq 1 60); do
  curl -fs http://127.0.0.1:18080/api/health >/dev/null 2>&1 && break
  sleep 2
done
health=$(curl -fs http://127.0.0.1:18080/api/health) || fail "API 헬스가 응답하지 않는다"
echo "$health"
echo "$health" | grep -q "\"$VERSION" || fail "API 버전 표시가 $VERSION 이 아니다"

token=$(curl -fs -X POST http://127.0.0.1:18080/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"r2","password":"admin"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["accessToken"])') \
  || fail "시험 계정 로그인 실패"
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $token" \
  http://127.0.0.1:18080/api/help/tool-integration)
[ "$code" = 200 ] || fail "이미지 안 사용 안내 문서(/api/help) 응답 $code"
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $token" \
  http://127.0.0.1:18080/api/projects)
[ "$code" = 200 ] || fail "사업 목록 응답 $code"
code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/api/projects)
[ "$code" = 401 ] || fail "비로그인 사업 목록이 401 이 아니다($code)"
unset token
echo "로그인·사용 안내·사업 목록·비로그인 거절 확인"

echo "== 웹 (/ax-link/)"
docker run -d --name smoke-web --network "$NET" -p 127.0.0.1:18081:8080 \
  -e AXLINK_API_UPSTREAM=http://api:8080 -e AXLINK_BASE_PATH=/ax-link/ \
  -e AXLINK_SERVER_NAMES="localhost 127.0.0.1" -e AXLINK_LOCAL_NAMES="localhost 127.0.0.1" \
  "$WEB" >/dev/null
for _ in $(seq 1 30); do
  curl -fs http://127.0.0.1:18081/ax-link/ >/dev/null 2>&1 && break
  sleep 1
done
html=$(curl -fs http://127.0.0.1:18081/ax-link/) || fail "웹 /ax-link/ 가 응답하지 않는다"
assets=$(echo "$html" | grep -oE '(src|href)="[^"]*/assets/[^"]+"' | sed -E 's/^[a-z]+="//; s/"$//')
[ -n "$assets" ] || fail "index.html 이 assets 를 부르지 않는다"
for a in $assets; do
  case "$a" in /ax-link/assets/*) ;; *) fail "앱 경로 밖 자산: $a" ;; esac
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:18081$a")
  [ "$code" = 200 ] || fail "자산 $a 응답 $code"
done
echo "$assets" | grep -q '\.js$' || fail "JS 자산이 없다"
echo "$assets" | grep -q '\.css$' || fail "CSS 자산이 없다"
curl -fs http://127.0.0.1:18081/ax-link/version.json | grep -q "\"$VERSION\"" \
  || fail "웹 version.json 이 $VERSION 이 아니다"
curl -fs http://127.0.0.1:18081/ax-link/api/health >/dev/null || fail "웹의 API 프록시 실패"
code=$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: evil.example' http://127.0.0.1:18081/ax-link/)
[ "$code" = 421 ] || fail "목록 밖 호스트가 421 이 아니다($code)"
loc=$(curl -s -o /dev/null -D - 'http://127.0.0.1:18081/p/x/requirements?q=1' | tr -d '\r' | sed -n 's/^[Ll]ocation: //p')
[ "$loc" = "/ax-link/p/x/requirements?q=1" ] || fail "앱 경로 없는 화면 주소가 앱 경로로 가지 않는다($loc)"
code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18081/ax-link/p/x/requirements)
[ "$code" = 200 ] || fail "앱 경로 화면 주소 응답 $code"
echo "웹 자산 $(echo "$assets" | wc -l)개, API 프록시, 호스트 제한, 앱 경로 없는 주소 이동 확인"
