// 빌드 결과 검사. 화면이 자기 JS·CSS 를 앱 경로 아래에서 찾는지 본다.
//
//   AXLINK_BASE_PATH=/ax-link/ node scripts/check-build.mjs [dist 경로]
//
// 10-07 5174 웹 이미지가 `/Program Files/Git/ax-link/assets/...` 를 불러 흰 화면이 됐다. Git Bash 가
// 빌드 인자를 Windows 경로로 바꿨다. 첫 HTML 은 200 이라 응답 코드로는 안 잡힌다.
// 웹 이미지 빌드(docker/web.Dockerfile)와 CI 가 이 검사를 돌린다. 실패하면 0 이 아닌 값으로 끝난다.
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

const dist = path.resolve(process.argv[2] ?? 'dist');
const base = process.env.AXLINK_BASE_PATH ?? '/';
const problems = [];

// vite.config.ts 와 같은 규칙
if (!/^\/([A-Za-z0-9._-]+\/)*$/.test(base)) {
  problems.push(`AXLINK_BASE_PATH 가 URL 경로가 아니다: "${base}"`);
}

// 호스트 경로가 섞인 흔적. 드라이브 문자(C:/), Git Bash 설치 경로, 역슬래시
// (https:// 의 "s:/" 는 앞에 글자가 붙어 있어 드라이브 문자로 보지 않는다)
const HOST_PATH = /(\/Program Files\/|Program%20Files|(^|["'(=\s])[A-Za-z]:[\\/]|\\\\)/;

const indexFile = path.join(dist, 'index.html');
if (!existsSync(indexFile)) {
  problems.push(`${indexFile} 가 없다`);
} else {
  const html = readFileSync(indexFile, 'utf8');
  if (HOST_PATH.test(html)) problems.push('index.html 에 호스트 경로가 들어 있다');
  const refs = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map((m) => m[1]);
  const assets = refs.filter((r) => r.includes('/assets/'));
  if (assets.length === 0) problems.push('index.html 이 assets 의 JS·CSS 를 하나도 부르지 않는다');
  if (!assets.some((r) => r.endsWith('.js'))) problems.push('index.html 에 JS 가 없다');
  for (const ref of assets) {
    if (!ref.startsWith(`${base}assets/`)) {
      problems.push(`자산 경로가 앱 경로(${base}) 아래가 아니다: ${ref}`);
      continue;
    }
    const file = path.join(dist, ref.slice(base.length));
    if (!existsSync(file)) problems.push(`index.html 이 부르는 파일이 없다: ${ref}`);
  }
}

// CSS 안의 url() 과 JS 의 기준 경로에도 호스트 경로가 없어야 한다
const assetDir = path.join(dist, 'assets');
if (existsSync(assetDir)) {
  for (const name of readdirSync(assetDir)) {
    if (!/\.(js|css)$/.test(name)) continue;
    const text = readFileSync(path.join(assetDir, name), 'utf8');
    if (/\/Program Files\/|Program%20Files/.test(text)) {
      problems.push(`assets/${name} 에 호스트 경로가 들어 있다`);
    }
  }
}

if (problems.length > 0) {
  console.error(`빌드 검사 실패 (앱 경로 ${base}, ${dist})`);
  for (const p of problems) console.error(`- ${p}`);
  process.exit(1);
}
console.log(`빌드 검사 통과: 자산이 ${base}assets/ 아래에 있다 (${dist})`);
