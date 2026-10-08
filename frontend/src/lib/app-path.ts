/**
 * 앱이 놓인 경로. 빌드의 base 값이다(로컬 개발은 '/', 외부 공개는 '/ax-link/'). 끝은 늘 '/'.
 * 같은 도메인에 다른 서비스가 있어서 /api 나 /assets 를 도메인 맨 앞에 두면 안 된다.
 */
export const APP_BASE: string = import.meta.env.BASE_URL;

/** 라우터 basename. '/' 면 비워 둔다. */
export const ROUTER_BASENAME: string | undefined =
  APP_BASE === '/' ? undefined : APP_BASE.replace(/\/$/, '');

/** 서버가 준 '/...' 화면 경로를 앱 경로 아래로 옮긴다. 바깥 주소(http…)는 그대로 둔다. */
export function appHref(path: string): string {
  if (!path.startsWith('/') || path.startsWith('//')) return path;
  return APP_BASE.replace(/\/$/, '') + path;
}

/**
 * 서버가 준 '/api/...' 내려받기 주소면 API 경로('/documents/...')를 돌려준다. 아니면 null.
 * 이 주소는 토큰이 있어야 열려서 링크로 걸 수 없다. lib/http 의 download 로 받는다.
 */
export function apiDownloadPath(url: string | null | undefined): string | null {
  return url && url.startsWith('/api/') ? url.slice('/api'.length) : null;
}
