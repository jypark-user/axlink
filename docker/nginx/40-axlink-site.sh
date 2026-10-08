#!/bin/sh
# AX Link 웹 설정을 기동 때 만든다. 공식 이미지가 /docker-entrypoint.d/ 의 스크립트를 nginx 전에 돌린다.
#
#   AXLINK_API_UPSTREAM   API 주소. 기본 http://api:8080
#   AXLINK_BASE_PATH      앱 경로. 기본 /. 외부 공개는 /ax-link/ (빌드의 base 와 같아야 한다)
#   AXLINK_SERVER_NAMES   받을 호스트(공백 구분). 비우면 가리지 않는다. 목록 밖 호스트는 421
#   AXLINK_LOCAL_NAMES    그중 첫 화면(/)을 앱 경로로 보낼 호스트. 프록시 없이 직접 여는 주소
#
# 앞단 프록시가 앱 경로를 떼고 넘기든 붙여 넘기든 같은 화면이 나오게, 앱 경로로 온 요청은
# 떼어 낸 경로로 다시 찾는다. 앞단이 떼는 경우 "/" 가 첫 화면이라 그 호스트는 "/" 를 돌려보내지 않는다.
set -eu

upstream="${AXLINK_API_UPSTREAM:-http://api:8080}"
base="${AXLINK_BASE_PATH:-/}"
names="${AXLINK_SERVER_NAMES:-}"
local_names="${AXLINK_LOCAL_NAMES:-}"
out=/etc/nginx/conf.d/default.conf

case "$base" in
  /) prefix="" ;;
  /*/) prefix="${base%/}" ;;
  *) echo "AXLINK_BASE_PATH 는 / 로 시작하고 / 로 끝나야 한다: $base" >&2; exit 1 ;;
esac

# 화면·API 공통 위치. 앱 경로는 떼어 낸 뒤 이 위치들이 받는다.
locations() {
  if [ -n "$prefix" ]; then
    cat <<EOF
    location = ${prefix} { return 301 ${prefix}/; }
    location = ${prefix}/ { rewrite ^ /index.html last; }
    location ^~ ${prefix}/ { rewrite ^${prefix}/(.*)\$ /\$1 last; }
EOF
  fi
  cat <<EOF
    location /api/ {
        proxy_pass ${upstream};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";
        # AI 답변은 SSE 로 조각조각 온다. 모아 두면 화면에 한 번에 나온다.
        # 앞단 프록시도 모아 두지 않게 API 의 X-Accel-Buffering 을 그대로 넘긴다.
        proxy_buffering off;
        proxy_cache off;
        proxy_pass_header X-Accel-Buffering;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # 빌드 산출물은 파일명에 해시가 붙어 오래 캐시해도 된다.
    location /assets/ {
        try_files \$uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    location = /version.json {
        add_header Cache-Control "no-store";
        try_files \$uri =404;
    }

    # 화면 주소를 직접 열거나 새로고침해도 index.html 이 받는다(클라이언트 라우팅).
    location / {
        try_files \$uri \$uri/ /index.html;
        add_header Cache-Control "no-cache";
    }
EOF
}

server_block() {  # $1 server_name, $2 첫 화면을 앱 경로로 보낼지(yes/no), $3 listen 추가 인자
  cat <<EOF
server {
    listen 8080${3:+ $3};
    server_name $1;
    root /usr/share/nginx/html;
    # 문서 업로드. API 쪽 제한보다 작으면 여기서 먼저 끊긴다.
    client_max_body_size 100m;
    absolute_redirect off;
EOF
  if [ "$2" = yes ] && [ -n "$prefix" ]; then
    echo "    location = / { return 302 ${prefix}/; }"
  fi
  locations
  echo "}"
}

{
  echo "# 40-axlink-site.sh 가 기동 때 만든 파일이다. 고치려면 환경변수를 바꾼다."
  if [ -z "$names" ]; then
    server_block "_" yes "default_server"
  else
    echo "server { listen 8080 default_server; server_name _; return 421; }"
    remote=""
    for n in $names; do
      case " $local_names " in *" $n "*) ;; *) remote="$remote $n" ;; esac
    done
    [ -n "$local_names" ] && server_block "$local_names" yes ""
    [ -n "${remote# }" ] && server_block "${remote# }" no ""
  fi
} > "$out"
echo "AX Link 웹 설정: 앱 경로 ${base}, 호스트 ${names:-(가리지 않음)}"
