#!/bin/sh
# 개발용 웹 컨테이너 진입점. node_modules 는 이름 있는 볼륨이라 package-lock.json 이 바뀌어도
# 저절로 따라오지 않는다. 잠금 파일 해시가 다르면 다시 깐다.
set -e
cd /web
want=$(sha256sum package-lock.json | cut -d' ' -f1)
have=$(cat node_modules/.lock-hash 2>/dev/null || true)
if [ "$want" != "$have" ]; then
  echo "package-lock.json 이 바뀌어 npm ci 를 다시 실행한다"
  npm ci --no-audit --no-fund
  echo "$want" > node_modules/.lock-hash
fi
exec "$@"
