// 반영 뒤 화면 점검. 첫 HTML 과 API 의 200 만으로는 화면이 뜨는지 모른다(10-07 5174 흰 화면).
//
//   SMOKE_URL=http://localhost:5174/ax-link SMOKE_USER=<아이디> SMOKE_PASSWORD=<비밀번호> \
//   SMOKE_CHROME="C:/Program Files/Google/Chrome/Application/chrome.exe" \
//   node scripts/smoke-web.mjs
//
// 보는 것: 앱 경로의 JS·CSS 로딩(형식까지), 앱 렌더링, 로그인, 보호 화면 직접 접근과 새로고침,
// 콘솔 오류, 실패한 네트워크 요청. 비밀번호는 환경변수로만 받고 출력하지 않는다.
// 하나라도 실패하면 0 이 아닌 값으로 끝난다. 화면 사진은 SMOKE_OUT 폴더(기본 ./smoke-out)에 남긴다.
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright-core';

const base = (process.env.SMOKE_URL ?? '').replace(/\/+$/, '');
const user = process.env.SMOKE_USER;
const password = process.env.SMOKE_PASSWORD;
const chrome = process.env.SMOKE_CHROME;
const out = process.env.SMOKE_OUT ?? 'smoke-out';
if (!base || !user || !password || !chrome) {
  console.error('SMOKE_URL·SMOKE_USER·SMOKE_PASSWORD·SMOKE_CHROME 가 필요하다');
  process.exit(2);
}
const appPath = new URL(`${base}/`).pathname; // 예: /ax-link/
mkdirSync(out, { recursive: true });

const results = [];
const check = (name, ok, detail = '') => {
  results.push(ok);
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
};

const browser = await chromium.launch({ executablePath: chrome, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'ko-KR' });
const consoleErrors = [];
const failed = [];
const badAssets = [];
page.on('console', (m) => m.type() === 'error' && consoleErrors.push(m.text()));
page.on('pageerror', (e) => consoleErrors.push(String(e)));
page.on('requestfailed', (r) => failed.push(`${r.failure()?.errorText ?? 'failed'} ${r.url()}`));
page.on('response', (r) => {
  const url = new URL(r.url());
  if (r.status() >= 400) failed.push(`${r.status()} ${url.pathname}`);
  if (/\.(js|css)$/.test(url.pathname)) {
    const type = r.headers()['content-type'] ?? '';
    const want = url.pathname.endsWith('.js') ? 'javascript' : 'css';
    if (!url.pathname.startsWith(`${appPath}assets/`) || !type.includes(want)) {
      badAssets.push(`${r.status()} ${url.pathname} ${type}`);
    }
  }
});

const rendered = async () =>
  page.evaluate(() => (document.getElementById('root')?.children.length ?? 0) > 0);

try {
  // 1. 첫 화면: 자산 로딩과 렌더링
  await page.goto(`${base}/`, { waitUntil: 'networkidle' });
  check('앱 경로 아래 JS·CSS 를 형식 맞게 받는다', badAssets.length === 0, badAssets.join(' | '));
  check('앱이 그려진다', await rendered());
  check('로그인 화면으로 간다', page.url().includes('/login'), new URL(page.url()).pathname);
  await page.screenshot({ path: path.join(out, '1-login.png') });

  // 2. 로그인
  await page.fill('#username', user);
  await page.fill('#password', password);
  await page.click('button[type=submit]');
  await page.waitForURL((u) => !u.pathname.includes('/login'), { timeout: 40000 });
  check('로그인된다', !page.url().includes('/login'), new URL(page.url()).pathname);

  // 3. 보호 화면 직접 접근과 새로고침
  await page.goto(`${base}/projects`, { waitUntil: 'networkidle' });
  check('사업 목록에 바로 들어간다', !page.url().includes('/login') && (await rendered()));
  const href = await page
    .locator(`a[href*="${appPath}p/"], a[href^="/p/"]`)
    .first()
    .getAttribute('href')
    .catch(() => null);
  const projectId = href ? /\/p\/([^/?#]+)/.exec(href)?.[1] : null;
  const deep = projectId ? `${appPath}p/${projectId}/documents` : null;
  if (deep) {
    await page.goto(new URL(deep, base).toString(), { waitUntil: 'networkidle' });
    check(
      '사업 화면 주소로 바로 들어간다',
      !page.url().includes('/login') && (await rendered()),
      deep,
    );
    await page.reload({ waitUntil: 'networkidle' });
    check('새로고침해도 그 화면이다', page.url().endsWith(deep) && (await rendered()), deep);
  } else {
    check('사업 화면 주소를 찾는다', false, '사업 목록에 링크가 없다');
  }
  await page.screenshot({ path: path.join(out, '2-protected.png') });
  await page.goto(`${base}/templates`, { waitUntil: 'networkidle' });
  await page.reload({ waitUntil: 'networkidle' });
  check(
    '인포 템플릿 화면을 새로고침해도 그려진다',
    page.url().endsWith('/templates') && (await rendered()),
  );

  check('콘솔 오류가 없다', consoleErrors.length === 0, consoleErrors.slice(0, 5).join(' | '));
  check('실패한 요청이 없다', failed.length === 0, failed.slice(0, 5).join(' | '));
  check('잘못된 자산이 없다', badAssets.length === 0, badAssets.slice(0, 5).join(' | '));
} catch (e) {
  check('점검을 끝까지 돌린다', false, String(e).split('\n')[0]);
} finally {
  await browser.close();
}

const ok = results.every(Boolean);
console.log(ok ? '화면 점검 통과' : '화면 점검 실패');
process.exit(ok ? 0 : 1);
