# AX-Link 물리 설계 — 프론트엔드

| 항목 | 내용 |
| --- | --- |
| 문서 ID | `design/03-physical-frontend` |
| 버전 | v1.0 (2026-08-20) |
| 상위 원천 | `docs/AX-Link-PRD.md` §4·§6, `design/01-conceptual-architecture.md`, `design/02-logical-frontend.md`, `design/02-logical-api.md` |
| 범위 | 패키지 구성 · shadcn 컴포넌트 목록 · 전체 파일 트리 · 타입 정의 · 위젯 레지스트리 · SSE 소비 · 테스트 · 디자인 토큰 |
| 계약 지위 | **구현 에이전트는 이 문서의 파일 경로·export 이름·시그니처를 그대로 만든다.** 여기 없는 파일·의존성을 추가하지 않는다 |
| 루트 | `frontend/` (프로젝트 루트 `/Users/userinsight-design/Documents/SourceCode/ax-link/frontend`) |

DTO 필드는 `02-logical-api.md` §3·§5 가 원천이다. 이 문서는 그것을 TypeScript 파일로 물리화할 뿐 필드를 추가·변경하지 않는다.

---

## 0. 채택하지 않은 것과 그 이유

이 절이 없으면 구현 에이전트가 관례적으로 추가한다. 명시적으로 금지한다.

| 후보 | 결정 | 근거 |
| --- | --- | --- |
| `@tanstack/react-query` | **미채택** | 화면 데이터가 대부분 "라우트 진입 시 1회 조회 + 액션 후 재조회"다. 필요한 것은 `data/loading/error/reload` 네 개뿐이고 `src/hooks/use-resource.ts` 40줄로 끝난다. 캐시 무효화 그래프·devtools·suspense 통합은 쓰지 않는 기능이다. `01-conceptual-architecture.md` §Presentation 의 "TanStack Query 훅" 표기는 이 문서로 대체된다 |
| `axios` | **미채택** | `fetch` + `lib/http.ts` 로 충분하다. 인터셉터가 필요한 지점은 401 재발급 1곳뿐이다 |
| `zustand` / `redux` | **미채택** | 전역 상태는 인증 principal 하나다. `AuthContext` 로 끝난다. 대시보드 편집 상태는 페이지 로컬이다 |
| `date-fns` (직접 의존) | **미채택** | 표시용 포맷은 `Intl.DateTimeFormat('ko-KR')` 로 처리한다(`lib/format.ts`). `react-day-picker` 가 내부 의존으로 이미 끌고 오지만 우리 코드는 import 하지 않는다 |
| `react-markdown` | **미채택** | Q&A 답변은 문단 + 각주 `[n]` 만 렌더한다. 마크다운 파서 대신 `parseFootnotes()` 정규식 1개로 처리한다(§6.4). LLM 출력에 원시 HTML 을 넣지 않으므로 sanitizer 도 불필요하다 |
| `@types/react-grid-layout` | **미채택** | v2.2.4 는 `dist/index.d.ts` 를 자체 배포한다. DefinitelyTyped 패키지는 v1 형태라 오히려 충돌한다 |
| `typescript@7` | **미채택** | 레지스트리 최신은 7.0.2 이나 `typescript-eslint@8` 의 peer 가 `>=4.8.4 <6.1.0` 이다. `~5.9.3` 으로 고정한다 |
| `embla-carousel-react`, `input-otp`, `vaul` | **미채택** | 대응 shadcn 컴포넌트(carousel/input-otp/drawer)를 쓰지 않는다 |
| MSW (mock service worker) | **미채택** | PRD §6.1.1 "프론트에 목업 데이터 파일 금지". 테스트는 `globalThis.fetch` 를 `vi.fn()` 으로 대체한다 |

---

## 1. 프로젝트 구성 확정

### 1.1 `frontend/package.json`

```json
{
  "name": "ax-link-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "lint": "eslint . --max-warnings 0",
    "format": "prettier --write \"src/**/*.{ts,tsx,css}\"",
    "format:check": "prettier --check \"src/**/*.{ts,tsx,css}\"",
    "typecheck": "tsc -b --noEmit"
  },
  "dependencies": {
    "@hookform/resolvers": "^5.9.1",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "cmdk": "^1.1.1",
    "lucide-react": "^1.33.0",
    "radix-ui": "^1.6.7",
    "react": "^19.2.8",
    "react-day-picker": "^10.0.1",
    "react-dom": "^19.2.8",
    "react-grid-layout": "^2.2.4",
    "react-hook-form": "^7.85.0",
    "react-is": "^19.2.8",
    "react-router-dom": "^7.18.2",
    "recharts": "^3.10.1",
    "sonner": "^2.0.8",
    "tailwind-merge": "^3.6.0",
    "zod": "^4.4.3"
  },
  "devDependencies": {
    "@eslint/js": "^10.0.1",
    "@tailwindcss/vite": "^4.3.3",
    "@testing-library/dom": "^10.4.1",
    "@testing-library/jest-dom": "^7.0.1",
    "@testing-library/react": "^16.3.2",
    "@testing-library/user-event": "^14.6.5",
    "@types/node": "^26.2.0",
    "@types/react": "^19.2.18",
    "@types/react-dom": "^19.2.4",
    "@types/react-is": "^19.2.0",
    "@vitejs/plugin-react": "^6.1.0",
    "@vitest/coverage-v8": "^4.1.11",
    "eslint": "^10.8.1",
    "eslint-config-prettier": "^10.1.8",
    "eslint-plugin-react-hooks": "^7.1.1",
    "eslint-plugin-react-refresh": "^0.5.4",
    "globals": "^17.11.0",
    "jsdom": "^30.0.1",
    "prettier": "^3.9.6",
    "tailwindcss": "^4.3.3",
    "tw-animate-css": "^1.4.0",
    "typescript": "~5.9.3",
    "typescript-eslint": "^8.67.0",
    "vite": "^8.2.2",
    "vitest": "^4.1.11"
  }
}
```

의존성 17개 / 개발 의존성 26개. 각 항목의 존재 이유:

| 패키지 | 왜 필요한가 | 없으면 |
| --- | --- | --- |
| `radix-ui` | shadcn 컴포넌트 35종의 프리미티브. **단일 통합 패키지**를 쓰고 `@radix-ui/react-*` 개별 패키지를 추가하지 않는다 | 접근성 있는 dialog/select/dropdown 을 직접 구현해야 함 |
| `class-variance-authority` · `clsx` · `tailwind-merge` | shadcn `cn()` 및 variant 정의의 필수 3종 | shadcn 소스가 컴파일 안 됨 |
| `lucide-react` | shadcn 기본 아이콘 세트 (`components.json.iconLibrary`) | 아이콘 없음 |
| `recharts` + `react-is` | shadcn `chart` 래퍼의 백엔드. `react-is` 는 recharts peer | bar/line/pie 위젯 4종 불가 |
| `react-grid-layout` | ADR-009 예외 허용 기능 라이브러리. 대시보드 드래그·리사이즈 | PRD 4.3.1 미충족 |
| `react-hook-form` + `zod` + `@hookform/resolvers` | shadcn `form` 컴포넌트가 react-hook-form 위에 세워져 있다. PRD §6.2 가 "Form(react-hook-form + zod)" 로 명시 | 프로젝트 생성·연동 등록·검수 등록 등 10개 폼의 필드 오류 상태를 직접 구현 |
| `react-day-picker` | shadcn `calendar` 의 백엔드. PRD §6.2 가 착수일·마감일에 Calendar + Popover 를 명시 | 날짜 범위 검증 UI 없음 |
| `cmdk` | shadcn `command` 의 백엔드. 용역사 계정 검색 | Command 팔레트 불가 |
| `sonner` | shadcn `sonner` 의 백엔드. 앱 셸 toast | 액션 결과 알림 없음 |
| `tw-animate-css` | Tailwind v4 에서 shadcn 이 쓰는 `animate-in`/`fade-in` 유틸 제공(v3 의 `tailwindcss-animate` 대체) | dialog/sheet/dropdown 애니메이션 클래스가 no-op |
| `@types/node` | `vite.config.ts` 의 `path`·`fileURLToPath` | alias 설정 타입 오류 |

### 1.2 `frontend/vite.config.ts`

```ts
/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reportsDirectory: 'coverage',
      include: ['src/lib/**', 'src/hooks/**', 'src/features/**', 'src/standard/**'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/components/ui/**'],
    },
  },
});
```

프록시 규칙 3가지를 고정한다.

| 규칙 | 값 | 근거 |
| --- | --- | --- |
| `ws` | 설정하지 않음 | WebSocket 을 쓰지 않는다. SSE 는 일반 HTTP 다 |
| `rewrite` | 설정하지 않음 | 백엔드도 `/api` 베이스다(`02-logical-api.md` §1.1). 경로를 그대로 넘긴다 |
| 버퍼링 | 별도 설정 없음 | Vite 5+ 프록시는 SSE 를 버퍼링하지 않는다. 서버가 `X-Accel-Buffering: no` 를 보낸다 |

### 1.3 tsconfig 3분할

`tsconfig.json` (솔루션 파일, 컴파일 대상 없음):

```json
{
  "files": [],
  "references": [{ "path": "./tsconfig.app.json" }, { "path": "./tsconfig.node.json" }]
}
```

`tsconfig.app.json`:

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "target": "ES2023",
    "lib": ["ES2023", "DOM", "DOM.Iterable", "DOM.AsyncIterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "useDefineForClassFields": true,
    "types": ["vite/client"],
    "skipLibCheck": true,
    "allowImportingTsExtensions": false,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true,
    "erasableSyntaxOnly": true,
    "exactOptionalPropertyTypes": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"]
}
```

`tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "target": "ES2023",
    "lib": ["ES2023"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "types": ["node"],
    "skipLibCheck": true,
    "verbatimModuleSyntax": true,
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  },
  "include": ["vite.config.ts", "vitest.setup.ts", "eslint.config.js"]
}
```

| 옵션 | 이유 |
| --- | --- |
| `DOM.AsyncIterable` | `for await (const chunk of stream)` 형태로 SSE 를 읽는다(§6). 이 lib 없으면 `ReadableStream` 이 async iterable 로 안 잡힌다 |
| `verbatimModuleSyntax` | `import type` 강제. DTO 전용 import 가 런타임 번들에 남지 않는다 |
| `exactOptionalPropertyTypes` | API 는 `null` 을 쓰고 `undefined` 를 쓰지 않는다(§1.1 null 정책). 이 옵션이 `?:` 와 `| null` 혼동을 컴파일 타임에 막는다 |
| `erasableSyntaxOnly` | enum·파라미터 프로퍼티 금지 → `as const` 객체 + union 타입만 남는다 |
| `noUncheckedSideEffectImports` | `import 'react-grid-layout/css/styles.css'` 오타를 잡는다 |

`any` 금지는 `tsconfig` 가 아니라 eslint 규칙(`@typescript-eslint/no-explicit-any: error`)으로 강제한다.

### 1.4 `frontend/components.json` (shadcn CLI 설정)

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/index.css",
    "baseColor": "slate",
    "cssVariables": true,
    "prefix": ""
  },
  "iconLibrary": "lucide",
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

`tailwind.config` 가 빈 문자열인 것은 Tailwind v4 규격이다(설정 파일이 없고 `index.css` 의 `@theme` 이 설정을 대신한다).

### 1.5 `frontend/index.html`

```html
<!doctype html>
<html lang="ko" class="light">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AX-Link</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

### 1.6 `frontend/vitest.setup.ts`

```ts
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

globalThis.matchMedia = ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;
```

`ResizeObserver`·`matchMedia` 스텁은 jsdom 미구현분이다. radix(popover/select), `use-mobile`, `react-grid-layout` 이 셋 다 이것을 요구한다.

### 1.7 `frontend/eslint.config.js`

```js
import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'node_modules'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended, prettier],
    languageOptions: { ecmaVersion: 2023, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',
      'no-restricted-syntax': [
        'error',
        {
          selector: 'ExportDefaultDeclaration',
          message: 'named export 만 사용한다.',
        },
      ],
      'no-restricted-properties': [
        'error',
        { object: 'localStorage', message: 'INV-27: 대시보드·위젯 상태의 단일 원천은 서버 DB 다.' },
      ],
      'no-restricted-globals': [
        'error',
        { name: 'localStorage', message: 'INV-27: 대시보드·위젯 상태의 단일 원천은 서버 DB 다.' },
      ],
    },
  },
  {
    files: ['**/*.test.{ts,tsx}', 'vitest.setup.ts'],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
);
```

`no-restricted-syntax` 로 `export default` 를 **린트 에러로 막는다**. 규칙을 문서에만 적어두면 지켜지지 않는다. `localStorage` 금지도 같은 이유로 린트로 강제한다.

### 1.8 `frontend/.prettierrc.json`

```json
{
  "semi": true,
  "singleQuote": true,
  "tabWidth": 2,
  "printWidth": 100,
  "trailingComma": "all",
  "arrowParens": "always",
  "endOfLine": "lf"
}
```

---

## 2. shadcn/ui 컴포넌트 확정 (35종)

### 2.1 생성 방침 — CLI 가 아니라 직접 작성

| 항목 | 결정 |
| --- | --- |
| 방법 | `src/components/ui/<name>.tsx` 를 **shadcn new-york 소스 규격대로 직접 작성**한다. `npx shadcn@latest add` 실행을 전제로 하지 않는다 |
| 근거 1 | CLI 는 `ui.shadcn.com` 레지스트리에 네트워크 접근이 필요하다. 오프라인·사내망 환경에서 빌드가 재현되지 않는다 |
| 근거 2 | CLI 는 파일을 덮어쓰며 우리가 손댄 토큰·variant 를 되돌린다. shadcn 의 설계 의도 자체가 "코드를 프로젝트가 소유한다"(ADR-009)이므로 소유권을 처음부터 프로젝트에 둔다 |
| 근거 3 | `components.json` 은 그대로 유지한다. 나중에 새 컴포넌트가 필요해지면 CLI 로 추가할 수 있고, 그때 생성되는 파일이 기존 파일과 같은 규격이라 충돌하지 않는다 |
| 규격 | ① `import { X as XPrimitive } from 'radix-ui'` (개별 `@radix-ui/react-*` 금지) ② `data-slot="<name>"` 속성 부착 ③ `cn()` 으로 className 병합 ④ variant 는 `cva` ⑤ named export 만 ⑥ `React.ComponentProps<typeof Primitive.Root>` 로 props 타입 |

### 2.2 컴포넌트 → 화면 매핑

| # | `components/ui/` 파일 | 프리미티브·백엔드 | 사용 화면 |
| --- | --- | --- | --- |
| 1 | `alert.tsx` | — (div + cva) | 연동 테스트 결과, 동기화 실패 배너, 공통 에러 상태 |
| 2 | `alert-dialog.tsx` | `radix-ui/AlertDialog` | 프로젝트 종료 확정, 위젯 삭제, 연결 삭제, 할당 해제, 대화 삭제 |
| 3 | `avatar.tsx` | `radix-ui/Avatar` | 앱 헤더 계정 메뉴, 이슈 담당자, 승인자 표시 |
| 4 | `badge.tsx` | `radix-ui/Slot` + cva | 프로젝트 상태·SI 단계, 산출물 4상태, 동기화 결과, 추적 끊김, KPI 증감, 추천 산출물 유형 |
| 5 | `breadcrumb.tsx` | `radix-ui/Slot` | 앱 셸 상단 경로 (프로젝트 > 화면) |
| 6 | `button.tsx` | `radix-ui/Slot` + cva | 전 화면 |
| 7 | `calendar.tsx` | `react-day-picker` | 프로젝트 착수일·마감일, 시정조치 기한, 위젯 기간 필터 |
| 8 | `card.tsx` | — | 프로젝트 카드, 위젯 컨테이너, 로그인, KPI, 출처 카드, 검수 화면 |
| 9 | `chart.tsx` | `recharts` | bar/line/pie 위젯 3종 + Q&A 집계 응답 미니차트 |
| 10 | `checkbox.tsx` | `radix-ui/Checkbox` | 용역사 계정 다중 선택, 매핑 규칙 enabled, 초안 요구사항 선택 |
| 11 | `collapsible.tsx` | `radix-ui/Collapsible` | Q&A 출처 카드 접기/펼치기, 동기화 오류 원문, 사이드바 프로젝트 그룹 |
| 12 | `command.tsx` | `cmdk` + `dialog` | 용역사 계정 검색, 프로젝트 스위처, 시맨틱 measure 선택 |
| 13 | `context-menu.tsx` | `radix-ui/ContextMenu` | 대시보드 캔버스 위젯 우클릭(편집·복제·삭제) |
| 14 | `dialog.tsx` | `radix-ui/Dialog` | 위젯 생성 마법사 3단계, 프로젝트 수정, 연결 등록, 매핑 규칙, 수동 추적 링크 |
| 15 | `dropdown-menu.tsx` | `radix-ui/DropdownMenu` | 계정 메뉴, 대화 관리, 대시보드 선택, 테이블 행 액션 |
| 16 | `form.tsx` | `react-hook-form` + `radix-ui/Label`·`Slot` | 로그인, 초대 수락, 프로젝트 생성·수정, 연결 등록, 검수확인서, 초안 확정 |
| 17 | `hover-card.tsx` | `radix-ui/HoverCard` | Q&A 각주 `[n]` 미리보기, 추적표 셀 대상 미리보기 |
| 18 | `input.tsx` | — | 전 폼, 테이블 필터, 검색 |
| 19 | `label.tsx` | `radix-ui/Label` | 전 폼 |
| 20 | `pagination.tsx` | — (`button` 재사용) | 목록 화면 전부(PageResponse 소비 지점) |
| 21 | `popover.tsx` | `radix-ui/Popover` | Calendar 컨테이너, 프로젝트 범위 선택, 컬럼 선택 |
| 22 | `progress.tsx` | `radix-ui/Progress` | 프로젝트 카드 산출물 승인률, progress-list 위젯, 업로드 진행률 |
| 23 | `radio-group.tsx` | `radix-ui/RadioGroup` | 위젯 마법사 1단계 템플릿 카탈로그 카드 8종, 매핑 재적용 방식 선택 |
| 24 | `scroll-area.tsx` | `radix-ui/ScrollArea` | Q&A 스레드·대화 목록, 긴 테이블 시트, 초안 요구사항 목록 |
| 25 | `select.tsx` | `radix-ui/Select` | 산출물 유형 확정(22종), 매핑 대상 엔티티, 상태 필터, 정렬 |
| 26 | `separator.tsx` | `radix-ui/Separator` | KPI 카드 구분, 사이드바 섹션, 상세 시트 |
| 27 | `sheet.tsx` | `radix-ui/Dialog` | 용역사 할당, 동기화 잡 상세, 산출물 상세, 모바일 사이드바 |
| 28 | `sidebar.tsx` | 조합(`sheet`·`tooltip`·`button`·`separator`·`skeleton`·`input`) + `useIsMobile` | 앱 셸 좌측 내비, Q&A 대화 목록 사이드바 |
| 29 | `skeleton.tsx` | — | 전 화면 로딩 상태, 위젯 로딩, Q&A 응답 대기 |
| 30 | `sonner.tsx` | `sonner` | 저장·삭제·동기화 기동 결과 알림 |
| 31 | `switch.tsx` | `radix-ui/Switch` | 대시보드 편집 모드, 할당 권한 토글 3종, 연결 활성/일시중지 |
| 32 | `table.tsx` | — | 동기화 현황, 산출물 점검표, 추적표, 변경·시정, 계정·조직, data-table 위젯 |
| 33 | `tabs.tsx` | `radix-ui/Tabs` | 변경·시정 2탭, 프로젝트 상세 섹션 |
| 34 | `textarea.tsx` | — | 프로젝트 설명, 위젯 프롬프트, Q&A 입력(자동 높이), 검수 조건 |
| 35 | `tooltip.tsx` | `radix-ui/Tooltip` | 동기화 오류 요약, 사이드바 아이콘 모드, 지표 설명, 추적 끊김 사유 |

**만들지 않는 shadcn 컴포넌트**: accordion, aspect-ratio, carousel, drawer, input-otp, menubar, navigation-menu, resizable, slider, toggle, toggle-group, toast(deprecated → sonner). 대응 화면이 없다.

### 2.3 상호 의존 관계 (작성 순서)

```
1차 (의존 없음): utils.ts → button, input, label, textarea, badge, card, separator,
                 skeleton, alert, table, progress, avatar, pagination, breadcrumb
2차 (radix 단독): checkbox, switch, radio-group, tabs, collapsible, scroll-area,
                 tooltip, popover, dropdown-menu, context-menu, hover-card, select,
                 dialog, alert-dialog
3차 (조합):      sheet(dialog 규격), command(cmdk+dialog), calendar(button+react-day-picker),
                 form(label), sonner(sonner), chart(recharts+card)
4차 (최상위):    sidebar (sheet+tooltip+button+separator+skeleton+input+useIsMobile)
```

---

## 3. 전체 파일 트리

### 3.1 루트 (11)

| 경로 | 책임 |
| --- | --- |
| `frontend/package.json` | §1.1 |
| `frontend/vite.config.ts` | §1.2 |
| `frontend/tsconfig.json` | §1.3 솔루션 |
| `frontend/tsconfig.app.json` | §1.3 앱 |
| `frontend/tsconfig.node.json` | §1.3 툴링 |
| `frontend/components.json` | §1.4 |
| `frontend/index.html` | §1.5 |
| `frontend/vitest.setup.ts` | §1.6 |
| `frontend/eslint.config.js` | §1.7 |
| `frontend/.prettierrc.json` | §1.8 |
| `frontend/.gitignore` | `node_modules dist coverage .vite *.tsbuildinfo` |

### 3.2 `src/` 최상위 (5)

| 경로 | 책임 | export |
| --- | --- | --- |
| `src/main.tsx` | React 루트 마운트, `index.css`·`react-grid-layout/css/styles.css` import | — |
| `src/App.tsx` | `BrowserRouter` + `AuthProvider` + `<Toaster />` + `<AppRoutes />` 조립 | `App` |
| `src/routes.tsx` | 라우트 트리 전체(§3.11) | `AppRoutes` |
| `src/index.css` | Tailwind v4 import + 디자인 토큰(§8) | — |
| `src/vite-env.d.ts` | `/// <reference types="vite/client" />` | — |

### 3.3 `src/lib/` (7)

| 경로 | 책임 | export |
| --- | --- | --- |
| `src/lib/utils.ts` | `clsx` + `twMerge` 병합 | `cn` |
| `src/lib/api-error.ts` | `ErrorResponse` 를 감싼 예외 타입, 필드 오류 추출 | `ApiError`, `isApiError`, `toFieldErrors` |
| `src/lib/token-store.ts` | access(메모리) / refresh(sessionStorage) 보관·구독 | `tokenStore` |
| `src/lib/http.ts` | fetch 래퍼, Bearer 부착, 401 단일비행 refresh, 204 처리, `ApiError` 변환 | `request`, `requestMultipart`, `openStream`, `setUnauthorizedHandler` |
| `src/lib/query.ts` | 객체 → 쿼리스트링(배열은 파라미터 반복, `null` 은 생략) | `toQueryString`, `type QueryParams` |
| `src/lib/sse.ts` | `ReadableStream` → `SseEvent` 비동기 제너레이터 파서(§6.2) | `parseSseStream`, `type SseEvent` |
| `src/lib/format.ts` | `Intl` 기반 날짜·시각·숫자·퍼센트·바이트 포맷, 기간 문자열 | `formatDate`, `formatDateTime`, `formatRelative`, `formatNumber`, `formatPercent`, `formatBytes`, `formatPeriod` |

### 3.4 `src/hooks/` (4)

| 경로 | 책임 | export |
| --- | --- | --- |
| `src/hooks/use-mobile.ts` | `matchMedia('(max-width: 767px)')` 구독 (sidebar 의존) | `useIsMobile` |
| `src/hooks/use-resource.ts` | 조회 훅. `AbortController` 자동 취소, `intervalMs` 폴링, `reload()` | `useResource`, `type ResourceState` |
| `src/hooks/use-mutation.ts` | 쓰기 훅. `pending`/`error`/`run()`, 성공 시 toast | `useMutation`, `type MutationState` |
| `src/hooks/use-ask-stream.ts` | Q&A SSE 상태 기계(§6.3) | `useAskStream`, `type AskStreamState` |

### 3.5 `src/types/` (1) · `src/standard/` (2)

| 경로 | 책임 | export |
| --- | --- | --- |
| `src/types/api.ts` | `02-logical-api.md` §3·§5 DTO 전량(§4 전문) | 타입 전체 |
| `src/standard/iso29110.ts` | 산출물 22종·SI 6단계·PM 4활동 단일 정의 + 화면 이름 | `WORK_PRODUCT_TYPES`, `WORK_PRODUCT_LABEL`, `WORK_PRODUCT_ACTIVITY`, `type WorkProductType`, `SI_PHASES`, `type SiPhase`, `PM_ACTIVITIES`, `type PmActivity` |
| `src/standard/labels.ts` | 상태·우선순위·심각도 enum → 한국어 라벨 + 배지 톤 | `STATUS_LABEL`, `STATUS_TONE`, `PRIORITY_LABEL`, `SEVERITY_LABEL`, `TOOL_LABEL` |

### 3.6 `src/api/` (13)

전 모듈 동일 규칙: `lib/http.ts` 의 `request` 만 호출하고, 인자·반환은 `types/api.ts` 타입만 쓴다. UI 를 import 하지 않는다.

| 경로 | 엔드포인트 | export |
| --- | --- | --- |
| `src/api/auth.ts` | `/api/auth/*` | `login`, `refresh`, `logout`, `getMe`, `previewInvitation`, `acceptInvitation` |
| `src/api/organizations.ts` | `/api/organizations` | `listOrganizations`, `createOrganization`, `getOrganization`, `updateOrganization` |
| `src/api/users.ts` | `/api/users` | `listUsers`, `createUser`, `getUser`, `updateUser`, `resendInvitation` |
| `src/api/projects.ts` | `/api/projects` | `listProjects`, `createProject`, `getProject`, `updateProject`, `getClosureCheck`, `closeProject` |
| `src/api/assignments.ts` | `/api/projects/{id}/assignments` | `listAssignments`, `createAssignments`, `updateAssignmentPermissions`, `revokeAssignment` |
| `src/api/connections.ts` | `/api/(projects/{id}/)connections` | `listConnections`, `createConnection`, `getConnection`, `updateConnection`, `deleteConnection`, `updateConnectionStatus`, `testConnectionDraft`, `testConnection`, `triggerSync`, `listMappingRules`, `replaceMappingRules` |
| `src/api/sync-jobs.ts` | `/api/sync-jobs` | `listSyncJobs`, `getSyncJob`, `retrySyncJob`, `cancelSyncJob` |
| `src/api/standard-entities.ts` | §2.8 표준 엔티티 전체 | `listRequirements`, `getRequirement`, `updateRequirementStatus`, `listIssues`, `getIssue`, `getWorkProductChecklist`, `getWorkProduct`, `updateWorkProductStatus`, `listRisks`, `listChangeRequests`, `updateChangeRequestStatus`, `listCorrectionActions`, `updateCorrectionActionStatus`, `getTraceability`, `listTraceLinks`, `createTraceLink`, `deleteTraceLink`, `listProgressRecords`, `getAcceptanceRecord`, `createAcceptanceRecord`, `listEntityHistory` |
| `src/api/dashboards.ts` | `/api/dashboards` | `listDashboards`, `createDashboard`, `getDashboard`, `updateDashboard`, `deleteDashboard`, `replaceDashboardLayout` |
| `src/api/widgets.ts` | `/api/widgets` | `generateWidget`, `previewWidget`, `createWidget`, `updateWidget`, `deleteWidget`, `fetchWidgetData` |
| `src/api/semantic.ts` | `/api/semantic` | `getSemanticCatalog`, `getSemanticMeasure` |
| `src/api/conversations.ts` | `/api/conversations` | `listConversations`, `createConversation`, `getConversation`, `updateConversation`, `deleteConversation`, `listMessages`, `sendFeedback`, `getSuggestedQuestions`, `askUrl` |
| `src/api/documents.ts` | `/api/documents` | `listDocuments`, `uploadDocument`, `getDocument`, `getDraft`, `confirmDraft`, `rejectDraft`, `deleteDocument`, `documentContentUrl` |

`askUrl(conversationId)` 은 URL 문자열만 만든다. 실제 스트리밍 호출은 `hooks/use-ask-stream.ts` 가 `openStream` 으로 수행한다.

### 3.7 `src/components/ui/` (35)

`alert.tsx` `alert-dialog.tsx` `avatar.tsx` `badge.tsx` `breadcrumb.tsx` `button.tsx` `calendar.tsx` `card.tsx` `chart.tsx` `checkbox.tsx` `collapsible.tsx` `command.tsx` `context-menu.tsx` `dialog.tsx` `dropdown-menu.tsx` `form.tsx` `hover-card.tsx` `input.tsx` `label.tsx` `pagination.tsx` `popover.tsx` `progress.tsx` `radio-group.tsx` `scroll-area.tsx` `select.tsx` `separator.tsx` `sheet.tsx` `sidebar.tsx` `skeleton.tsx` `sonner.tsx` `switch.tsx` `table.tsx` `tabs.tsx` `textarea.tsx` `tooltip.tsx`

export 이름은 shadcn new-york 규격 그대로다(`Button`+`buttonVariants`, `Card`/`CardHeader`/`CardTitle`/`CardDescription`/`CardAction`/`CardContent`/`CardFooter`, `ChartContainer`/`ChartTooltip`/`ChartTooltipContent`/`ChartLegend`/`ChartLegendContent`/`type ChartConfig`, `Sidebar`/`SidebarProvider`/`SidebarTrigger`/`SidebarInset`/`SidebarMenu`/… , `Form`/`FormField`/`FormItem`/`FormLabel`/`FormControl`/`FormDescription`/`FormMessage`/`useFormField`).

### 3.8 `src/components/layout/` (8)

| 경로 | 책임 | export |
| --- | --- | --- |
| `src/components/layout/auth-layout.tsx` | 로그인·초대 수락용 중앙 카드 레이아웃(사이드바 없음) | `AuthLayout` |
| `src/components/layout/app-shell.tsx` | `SidebarProvider` + `AppSidebar` + `SidebarInset` + `<Outlet />` | `AppShell` |
| `src/components/layout/project-shell.tsx` | `/p/:projectId` 하위 공통. 프로젝트 로드·403/404 처리·`ProjectContext` 제공 | `ProjectShell`, `useProjectContext` |
| `src/components/layout/app-sidebar.tsx` | 전역 내비(프로젝트 목록·통합 Q&A·관리), 역할별 항목 노출 | `AppSidebar` |
| `src/components/layout/project-nav.tsx` | 프로젝트 하위 10개 화면 내비 그룹 | `ProjectNav` |
| `src/components/layout/app-header.tsx` | `SidebarTrigger` + Breadcrumb + 우측 액션 슬롯 | `AppHeader` |
| `src/components/layout/user-menu.tsx` | Avatar + DropdownMenu(계정·조직·로그아웃) | `UserMenu` |
| `src/components/layout/page-header.tsx` | 화면 제목·설명·우측 액션 3슬롯 표준 헤더 | `PageHeader` |

### 3.9 `src/components/common/` (7)

| 경로 | 책임 | export |
| --- | --- | --- |
| `src/components/common/data-state.tsx` | 로딩/에러/빈값 3상태 표준 렌더. `<DataState state={...}>` 로 감싸면 자식은 성공 케이스만 신경 쓴다 | `DataState`, `LoadingState`, `ErrorState`, `EmptyState` |
| `src/components/common/status-badge.tsx` | enum 값 → `standard/labels.ts` 조회 → Badge 톤 매핑 | `StatusBadge` |
| `src/components/common/confirm-dialog.tsx` | 파괴적 액션 공통 AlertDialog (PRD §6.2) | `ConfirmDialog` |
| `src/components/common/pagination-bar.tsx` | `PageResponse<T>` 메타 + page/size 변경 콜백 | `PaginationBar` |
| `src/components/common/date-field.tsx` | Popover + Calendar + Button 조합 단일 날짜 필드(`yyyy-MM-dd` 문자열 in/out) | `DateField` |
| `src/components/common/project-scope-picker.tsx` | 권한 내 프로젝트 다중 선택(Popover + Command + Checkbox) | `ProjectScopePicker` |
| `src/components/common/tool-icon.tsx` | `ToolKind`/`UPLOAD`/`MANUAL` → lucide 아이콘 + 라벨 | `ToolIcon` |

### 3.10 `src/features/` (87)

#### `features/auth/` (4)

| 경로 | 책임 | export |
| --- | --- | --- |
| `auth-context.tsx` | `MeResponse` 보유, `login`/`logout`/`refreshMe`, 부팅 시 `getMe()` 복원 | `AuthProvider`, `useAuth` |
| `guards.tsx` | 3종 라우트 가드(§3.11) | `RequireAuth`, `RequireRole`, `RequireProject` |
| `login-page.tsx` | 로그인 폼(email·password), 성공 시 `from` 복귀 | `LoginPage` |
| `invite-accept-page.tsx` | `?token=` 프리뷰 조회 → 비밀번호 설정 → 자동 로그인 | `InviteAcceptPage` |

#### `features/projects/` (7)

| 경로 | 책임 | export |
| --- | --- | --- |
| `project-list-page.tsx` | `/projects`. 상태 필터·검색·페이지네이션 | `ProjectListPage` |
| `project-card.tsx` | `ProjectSummaryResponse` 1건 카드(승인률 Progress, 열린 시정·리스크 배지) | `ProjectCard` |
| `project-create-page.tsx` | `/projects/new`. 필수 4필드 폼 호스트 | `ProjectCreatePage` |
| `project-form.tsx` | 생성·수정 공용 폼. zod 스키마 + `startDate <= endDate`(INV-08) | `ProjectForm`, `projectFormSchema`, `type ProjectFormValues` |
| `project-edit-dialog.tsx` | 상세 화면의 수정 Dialog(같은 `ProjectForm` 재사용) | `ProjectEditDialog` |
| `project-overview-page.tsx` | `/p/:projectId`. 지표 카드 + 할당·연결 요약 + 최근 이력 | `ProjectOverviewPage` |
| `project-metrics-cards.tsx` | `ProjectMetrics` 6지표 KPI 카드 행 | `ProjectMetricsCards` |

#### `features/assignments/` (4)

| 경로 | 책임 | export |
| --- | --- | --- |
| `assignment-sheet.tsx` | 용역사 할당 Sheet 진입점(조직 선택 → 계정 선택 → 권한) | `AssignmentSheet` |
| `assignment-table.tsx` | 현재 할당 목록 + 권한 토글 + 해제 | `AssignmentTable` |
| `contractor-picker.tsx` | Command 로 CONTRACTOR 조직·계정 검색·다중 선택 | `ContractorPicker` |
| `permission-toggles.tsx` | `AssignmentPermissions` 3종 Switch | `PermissionToggles` |

#### `features/connections/` (7)

| 경로 | 책임 | export |
| --- | --- | --- |
| `connections-page.tsx` | `/p/:projectId/connections` | `ConnectionsPage` |
| `connection-list.tsx` | 연결 카드 목록(상태·마지막 동기화·건수·액션) | `ConnectionList` |
| `connection-form-dialog.tsx` | 등록·수정 Dialog. 도구 Select(GITHUB/REDMINE) | `ConnectionFormDialog` |
| `credential-fields.tsx` | 액세스 토큰 단일 필드(GITHUB: PAT / REDMINE: API Key) | `CredentialFields` |
| `connection-test-panel.tsx` | 저장 전 테스트 → `ToolConnectionTestResponse` 또는 422/502 원문 Alert | `ConnectionTestPanel` |
| `mapping-rules-dialog.tsx` | 매핑 규칙 전체 치환 + `reapply` RadioGroup | `MappingRulesDialog` |
| `mapping-rule-row.tsx` | 규칙 1행(sourceKind/sourceValue/targetEntity/산출물유형/statusMap/enabled) | `MappingRuleRow` |

#### `features/collection/` (4)

| 경로 | 책임 | export |
| --- | --- | --- |
| `collection-page.tsx` | `/p/:projectId/collection`. 잡 필터 + 30초 폴링 | `CollectionPage` |
| `sync-job-table.tsx` | 잡 목록 테이블(상태 배지·소요시간·재시도) | `SyncJobTable` |
| `sync-job-detail-sheet.tsx` | 잡 상세 + 도구 오류 원문 Collapsible | `SyncJobDetailSheet` |
| `sync-stats-cells.tsx` | `SyncJobStats` 5수치 렌더(`unmapped` 는 경고 톤, 실패 아님 — INV-21) | `SyncStatsCells` |

#### `features/documents/` (6)

| 경로 | 책임 | export |
| --- | --- | --- |
| `documents-page.tsx` | `/p/:projectId/documents` | `DocumentsPage` |
| `upload-dropzone.tsx` | 드래그&드롭 + Progress + 확장자·50MB 사전 차단 | `UploadDropzone` |
| `document-table.tsx` | 문서 목록. `structuring` 상태 행만 2초 폴링 | `DocumentTable` |
| `structuring-draft-page.tsx` | `/p/:projectId/documents/:documentId/draft` 초안 확정 화면 | `StructuringDraftPage` |
| `draft-form.tsx` | 유형(22종 Select) · 제목 · 버전 · 작성일 · PM/SI 활동 · 확정 상태 | `DraftForm` |
| `draft-requirement-editor.tsx` | 추출 요구사항 목록 편집·삭제·우선순위 변경 | `DraftRequirementEditor` |

#### `features/dashboard/` (6)

| 경로 | 책임 | export |
| --- | --- | --- |
| `dashboard-page.tsx` | `/p/:projectId/dashboard` 및 통합 `/dashboards/:dashboardId` | `DashboardPage` |
| `dashboard-picker.tsx` | 대시보드 선택 DropdownMenu + 생성·삭제 | `DashboardPicker` |
| `dashboard-toolbar.tsx` | 편집 모드 Switch, 새로고침, 위젯 추가, 저장/취소 | `DashboardToolbar` |
| `dashboard-grid.tsx` | `ResponsiveGridLayout` 래핑(§5.5) | `DashboardGrid` |
| `use-dashboard-editor.ts` | 편집 드래프트 상태 기계(§5.6) | `useDashboardEditor`, `type DashboardEditorState` |
| `layout-mapper.ts` | `DashboardLayout` ↔ rgl `ResponsiveLayouts` 변환(null↔undefined) | `toGridLayouts`, `toDashboardLayout`, `defaultGridItem` |

#### `features/widgets/` (18)

| 경로 | 책임 | export |
| --- | --- | --- |
| `template-catalog.ts` | 템플릿 8종의 표시 이름·설명·아이콘·기본 크기(마법사 1단계 원천) | `WIDGET_TEMPLATES`, `type WidgetTemplateMeta` |
| `renderer-registry.ts` | `template` → 렌더러 조회 1단계(§5.2) | `widgetRenderers`, `resolveWidgetRenderer` |
| `widget-types.ts` | 렌더러 공통 props·프레임 상태 타입(§5.1) | `type WidgetRendererProps`, `type WidgetRenderer`, `type WidgetViewState` |
| `widget-data.ts` | `WidgetDataResponse` → 차트 series / 테이블 컬럼 / 단일값 파생(§5.4) | `toSeries`, `toChartConfig`, `pickTotal`, `pickDelta`, `resolveColumns` |
| `widget-frame.tsx` | 공통 프레임: 제목·툴바·로딩·에러·빈값·드래그 핸들(§5.3) | `WidgetFrame` |
| `widget-host.tsx` | 위젯 1개의 데이터 페치 + 프레임 + 렌더러 결합 | `WidgetHost` |
| `renderers/stat-card-widget.tsx` | KPI 단일값 + 증감 배지 | `StatCardWidget` |
| `renderers/bar-chart-widget.tsx` | recharts Bar (stacked 옵션) | `BarChartWidget` |
| `renderers/line-chart-widget.tsx` | recharts Line/Area | `LineChartWidget` |
| `renderers/pie-chart-widget.tsx` | recharts Pie(도넛) | `PieChartWidget` |
| `renderers/progress-list-widget.tsx` | 항목별 Progress 목록 | `ProgressListWidget` |
| `renderers/data-table-widget.tsx` | 정렬·페이징 테이블 | `DataTableWidget` |
| `renderers/checklist-widget.tsx` | 22종 점검표 압축 뷰 | `ChecklistWidget` |
| `renderers/gantt-summary-widget.tsx` | 계획 대비 실적 막대(커스텀 SVG, div 스택) | `GanttSummaryWidget` |
| `renderers/unsupported-widget.tsx` | 미지원 `template` 폴백(§5.2) | `UnsupportedWidget` |
| `widget-wizard-dialog.tsx` | 3단계 Dialog 호스트 + 단계 상태 | `WidgetWizardDialog` |
| `wizard-step-template.tsx` | 1단계 템플릿 RadioGroup 카드 8종 | `WizardStepTemplate` |
| `wizard-step-content.tsx` | 2단계 프롬프트 Textarea 또는 카탈로그 measure 선택 + 범위 | `WizardStepContent` |
| `wizard-step-preview.tsx` | 3단계 생성 결과. `NOT_EXPRESSIBLE` 이면 "Q&A로 질문하기" 버튼 | `WizardStepPreview` |

> `widget-types.ts` 를 포함해 19개다. 표의 첫 행부터 세면 19행이지만 `renderers/` 하위 9개를 별도 디렉터리로 세면 파일 수는 동일하다. 아래 §3.12 집계는 19로 계산한다.

#### `features/ax-query/` (10)

| 경로 | 책임 | export |
| --- | --- | --- |
| `ask-page.tsx` | `/ask` · `/p/:projectId/ask`. Sidebar + 스레드 2단 레이아웃 | `AskPage` |
| `conversation-sidebar.tsx` | 새 대화·대화 목록(핀 우선)·이름변경·삭제 | `ConversationSidebar` |
| `conversation-thread.tsx` | 메시지 이력 + 스트리밍 중 임시 메시지 렌더 | `ConversationThread` |
| `message-bubble.tsx` | user/assistant 버블. 중지 배지·피드백 버튼 | `MessageBubble` |
| `answer-body.tsx` | 본문 텍스트 → 문단 + 각주 `[n]` 링크 치환 | `AnswerBody`, `parseFootnotes` |
| `footnote-link.tsx` | `[n]` HoverCard 미리보기 + 클릭 시 출처 카드 하이라이트 | `FootnoteLink` |
| `source-card-list.tsx` | 출처 목록 Collapsible + 활성 각주 스크롤·강조 | `SourceCardList` |
| `source-card.tsx` | 출처 1건(도구 아이콘·라벨·스니펫·딥링크·페이지) | `SourceCard` |
| `ask-composer.tsx` | 자동 높이 Textarea + 범위 선택 + 전송/중지 | `AskComposer` |
| `suggested-questions.tsx` | 추천 질문 칩 4개 | `SuggestedQuestions` |

#### `features/deliverables/` (4)

| 경로 | 책임 | export |
| --- | --- | --- |
| `deliverables-page.tsx` | `/p/:projectId/deliverables`. 승인률 헤더 + 22행 표 | `DeliverablesPage` |
| `checklist-table.tsx` | 22종 고정 행. `applicable=false` 는 흐리게, `none` 은 "없음" | `ChecklistTable` |
| `work-product-detail-sheet.tsx` | 상세 + 버전 이력 + 변경 이력 | `WorkProductDetailSheet` |
| `work-product-status-dialog.tsx` | 제출·승인·반려 전이(역할별 버튼 노출) | `WorkProductStatusDialog` |
| `features/traceability/` (4) | | |
| `traceability-page.tsx` | `/p/:projectId/traceability` | `TraceabilityPage` |
| `traceability-table.tsx` | 고정 헤더 추적표. `brokenAt` 하이라이트 | `TraceabilityTable` |
| `trace-cell-list.tsx` | `TraceCell[]` 렌더 + 외부 딥링크 | `TraceCellList` |
| `manual-link-dialog.tsx` | 수동 추적 링크 생성 | `ManualLinkDialog` |

> traceability 4개는 위 표 하단에 이어 붙였다. 디렉터리는 `features/traceability/` 로 분리한다.

#### `features/changes/` (4)

| 경로 | 책임 | export |
| --- | --- | --- |
| `changes-page.tsx` | `/p/:projectId/changes`. Tabs 2개 | `ChangesPage` |
| `change-request-table.tsx` | 변경요청 목록 + 상태 전이 | `ChangeRequestTable` |
| `correction-action-table.tsx` | 시정조치 목록 + `overdueDays` 경고 | `CorrectionActionTable` |
| `entity-status-dialog.tsx` | `EntityStatusUpdateRequest` 공용 전이 Dialog | `EntityStatusDialog` |

#### `features/closure/` (4)

| 경로 | 책임 | export |
| --- | --- | --- |
| `closure-page.tsx` | `/p/:projectId/closure` | `ClosurePage` |
| `closure-checklist.tsx` | `ClosureCheck[]` 3항목 통과/미통과 | `ClosureChecklist` |
| `acceptance-record-form.tsx` | 검수확인서 등록(인수자·인수일·조건·문서) | `AcceptanceRecordForm` |
| `close-project-dialog.tsx` | 종료 확정 AlertDialog + 409 사유 표시 | `CloseProjectDialog` |

#### `features/admin/` (5)

| 경로 | 책임 | export |
| --- | --- | --- |
| `organizations-page.tsx` | `/admin/organizations` | `OrganizationsPage` |
| `organization-form-dialog.tsx` | 조직 등록·수정 | `OrganizationFormDialog` |
| `users-page.tsx` | `/admin/users`. 초대 재발송 포함 | `UsersPage` |
| `user-form-dialog.tsx` | 계정 생성·수정 | `UserFormDialog` |
| `audit-page.tsx` | `/admin/audit`. `entityType`+`entityId` 필수 조회 | `AuditPage` |

#### `features/errors/` (2)

| 경로 | 책임 | export |
| --- | --- | --- |
| `not-found-page.tsx` | 404 라우트 | `NotFoundPage` |
| `forbidden-page.tsx` | 가드 거부 착지 화면 | `ForbiddenPage` |

### 3.11 라우트 트리 (`src/routes.tsx`)

```
<Routes>
  <Route element={<AuthLayout />}>
    /login                                    LoginPage                     익명
    /invite/accept                            InviteAcceptPage              익명
  </Route>

  <Route element={<RequireAuth><AppShell /></RequireAuth>}>
    /                       → Navigate to /projects
    /projects                                 ProjectListPage               전체
    /projects/new                             ProjectCreatePage             RequireRole CLIENT
    /ask                                      AskPage (통합 범위)            전체
    /ask/:conversationId                      AskPage                       전체
    /dashboards/:dashboardId                  DashboardPage (통합)          RequireRole CLIENT
    /admin/organizations                      OrganizationsPage             RequireRole SUPER_ADMIN,CLIENT
    /admin/users                              UsersPage                     RequireRole SUPER_ADMIN,CLIENT
    /admin/audit                              AuditPage                     RequireRole SUPER_ADMIN,CLIENT
    /403                                      ForbiddenPage
    *                                         NotFoundPage

    <Route path="/p/:projectId" element={<RequireProject><ProjectShell /></RequireProject>}>
      ''            (index)                   ProjectOverviewPage
      dashboard                               DashboardPage
      connections                             ConnectionsPage
      collection                              CollectionPage
      documents                               DocumentsPage
      documents/:documentId/draft             StructuringDraftPage
      deliverables                            DeliverablesPage
      traceability                            TraceabilityPage
      changes                                 ChangesPage
      closure                                 ClosurePage                   RequireRole CLIENT
      ask                                     AskPage (프로젝트 고정 범위)
      ask/:conversationId                     AskPage
    </Route>
  </Route>
</Routes>
```

가드 3종의 시그니처:

```ts
export const RequireAuth: (props: { children: ReactNode }) => ReactElement;
export const RequireRole: (props: { allow: Role[]; children: ReactNode }) => ReactElement;
export const RequireProject: (props: { children: ReactNode }) => ReactElement;
```

| 가드 | 판정 | 실패 시 |
| --- | --- | --- |
| `RequireAuth` | `useAuth().me !== null` | `<Navigate to="/login" state={{ from: location }} replace />` |
| `RequireRole` | `allow.includes(me.role)` | `<Navigate to="/403" replace />` |
| `RequireProject` | `me.allowedProjectIds.includes(params.projectId)` | `<Navigate to="/403" replace />` |

`RequireProject` 는 `allowedProjectIds` 만 본다. 세부 권한(`canReadDashboard` 등)은 라우트가 아니라 **화면 안에서** 판정한다 — 대시보드 탭 자체는 보이되 데이터 영역이 "권한 없음"으로 렌더된다. 라우트에서 막으면 서버 403 과 화면 상태가 두 곳에서 갈라진다.

부팅 시 `me` 가 아직 `null`(로딩 중)인 것과 미인증을 구분한다: `AuthProvider` 는 `status: 'booting' | 'authenticated' | 'anonymous'` 를 노출하고, `RequireAuth` 는 `booting` 동안 전체화면 `Skeleton` 을 렌더한다. 이 구분이 없으면 새로고침마다 로그인 화면이 깜빡인다.

### 3.12 파일 수 집계

| 구역 | 개수 |
| --- | --- |
| `src/` 최상위 | 5 |
| `src/lib/` | 7 |
| `src/hooks/` | 4 |
| `src/types/` + `src/standard/` | 3 |
| `src/api/` | 13 |
| `src/components/ui/` | 35 |
| `src/components/layout/` | 8 |
| `src/components/common/` | 7 |
| `src/features/` (auth 4 · projects 7 · assignments 4 · connections 7 · collection 4 · documents 6 · dashboard 6 · widgets 19 · ax-query 10 · deliverables 4 · traceability 4 · changes 4 · closure 4 · admin 5 · errors 2) | 90 |
| **구현 파일 소계** | **172** |
| 테스트 파일 (§7.3) | 9 |
| **`src/` 총계** | **181** |
| 루트 설정 파일 | 11 |

---

## 4. `src/types/api.ts` 전문

구현 에이전트는 아래를 그대로 복사한다. 필드 추가·이름 변경 금지(`02-logical-api.md` 가 계약).

```ts
import type {
  PmActivity,
  SiPhase,
  WorkProductType,
} from '@/standard/iso29110';

export type { PmActivity, SiPhase, WorkProductType };

export type Role = 'SUPER_ADMIN' | 'CLIENT' | 'CONTRACTOR';
export type OrgType = 'CLIENT' | 'CONTRACTOR' | 'PLATFORM';
export type UserStatus = 'invited' | 'active' | 'disabled';
export type ProjectStatus = 'planning' | 'active' | 'closing' | 'closed';
export type ToolKind = 'GITHUB' | 'REDMINE';
export type ConnectionStatus = 'draft' | 'verified' | 'active' | 'paused' | 'failed';
export type SyncJobKind = 'BACKFILL' | 'POLL' | 'WEBHOOK';
export type SyncJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type RequirementStatus =
  | 'defined'
  | 'designed'
  | 'implemented'
  | 'verified'
  | 'accepted'
  | 'rejected';
export type IssueStatus = 'open' | 'in_progress' | 'resolved' | 'closed';
export type WorkProductStatus = 'none' | 'draft' | 'submitted' | 'approved' | 'rejected';
export type RiskStatus = 'open' | 'mitigating' | 'closed';
export type ChangeRequestStatus =
  | 'requested'
  | 'reviewing'
  | 'approved'
  | 'rejected'
  | 'applied';
export type CorrectionActionStatus = 'open' | 'done' | 'overdue';
export type Priority = 'MUST' | 'SHOULD' | 'COULD' | 'WONT';
export type Severity = 'critical' | 'high' | 'medium' | 'low';
export type Likelihood = 'high' | 'medium' | 'low';
export type TraceEntityType = 'requirement' | 'issue' | 'work_product';
export type TraceLinkKind = 'designs' | 'implements' | 'tests' | 'delivers';
export type DocumentStatus =
  | 'uploaded'
  | 'extracting'
  | 'extracted'
  | 'structuring'
  | 'structured'
  | 'confirmed'
  | 'rejected'
  | 'failed';
export type WidgetTemplate =
  | 'stat-card'
  | 'bar-chart'
  | 'line-chart'
  | 'pie-chart'
  | 'progress-list'
  | 'data-table'
  | 'checklist'
  | 'gantt-summary';
export type MappingSourceKind = 'ISSUE_TYPE' | 'OBJECT_KIND' | 'TRACKER';
export type MappingTargetEntity =
  | 'requirement'
  | 'issue'
  | 'risk'
  | 'work_product'
  | 'trace_link'
  | 'progress_record';
export type FilterOp =
  | 'eq'
  | 'ne'
  | 'in'
  | 'not_in'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'between'
  | 'in_month'
  | 'last_n_days';

export interface PageResponse<T> {
  content: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
  hasNext: boolean;
}

export interface ErrorResponse {
  code: string;
  message: string;
  details: Record<string, unknown> | null;
  path: string;
  timestamp: string;
}

export interface FieldError {
  field: string;
  reason: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RefreshTokenRequest {
  refreshToken: string;
}

export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  user: MeResponse;
}

export interface MeResponse {
  userId: string;
  email: string;
  name: string;
  role: Role;
  organizationId: string;
  organizationName: string;
  organizationType: OrgType;
  allowedProjectIds: string[];
  permissionsByProject: Record<string, AssignmentPermissions>;
}

export interface AssignmentPermissions {
  canConfigureIntegration: boolean;
  canUploadDocument: boolean;
  canReadDashboard: boolean;
}

export interface InvitationPreviewResponse {
  email: string;
  name: string;
  organizationName: string;
  role: Role;
  expiresAt: string;
}

export interface AcceptInvitationRequest {
  token: string;
  password: string;
}

export interface OrganizationCreateRequest {
  name: string;
  type: OrgType;
  businessNo: string | null;
}

export interface OrganizationUpdateRequest {
  name: string | null;
  businessNo: string | null;
}

export interface OrganizationResponse {
  id: string;
  name: string;
  type: OrgType;
  businessNo: string | null;
  userCount: number;
  projectCount: number;
  createdAt: string;
}

export interface UserCreateRequest {
  organizationId: string;
  email: string;
  name: string;
  role: Role;
}

export interface UserUpdateRequest {
  name: string | null;
  role: Role | null;
  status: UserStatus | null;
}

export interface UserResponse {
  id: string;
  organizationId: string;
  organizationName: string;
  email: string;
  name: string;
  role: Role;
  status: UserStatus;
  lastLoginAt: string | null;
  createdAt: string;
}

export interface ProjectCreateRequest {
  name: string;
  startDate: string;
  endDate: string;
  description: string;
}

export interface ProjectUpdateRequest {
  name: string | null;
  startDate: string | null;
  endDate: string | null;
  description: string | null;
  currentSiPhase: SiPhase | null;
}

export interface ProjectSummaryResponse {
  id: string;
  name: string;
  status: ProjectStatus;
  startDate: string;
  endDate: string;
  currentSiPhase: SiPhase;
  clientOrgId: string;
  clientOrgName: string;
  contractorOrgNames: string[];
  requiredWorkProductApproved: number;
  requiredWorkProductTotal: number;
  openCorrectionActionCount: number;
  openRiskCount: number;
  updatedAt: string;
}

export interface ProjectDetailResponse {
  id: string;
  name: string;
  description: string;
  status: ProjectStatus;
  startDate: string;
  endDate: string;
  currentSiPhase: SiPhase;
  clientOrgId: string;
  clientOrgName: string;
  assignmentCount: number;
  connectionCount: number;
  defaultDashboardId: string;
  metrics: ProjectMetrics;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectMetrics {
  requirementTotal: number;
  requirementAccepted: number;
  issueOpen: number;
  riskOpen: number;
  workProductApproved: number;
  workProductTotal: number;
  traceabilityCoverage: number;
  lastSyncedAt: string | null;
}

export interface ProjectCloseRequest {
  confirmationNote: string | null;
}

export interface ProjectClosureResponse {
  projectId: string;
  closable: boolean;
  checks: ClosureCheck[];
}

export interface ClosureCheck {
  key:
    | 'ACCEPTANCE_RECORD_EXISTS'
    | 'REQUIRED_WORK_PRODUCTS_APPROVED'
    | 'NO_OPEN_CORRECTION_ACTION';
  satisfied: boolean;
  detail: string;
}

export interface AssignmentCreateRequest {
  contractorOrgId: string;
  userIds: string[];
  permissions: AssignmentPermissions;
}

export interface AssignmentPermissionUpdateRequest {
  permissions: AssignmentPermissions;
}

export interface AssignmentResponse {
  id: string;
  projectId: string;
  contractorOrgId: string;
  contractorOrgName: string;
  userId: string;
  userName: string;
  userEmail: string;
  permissions: AssignmentPermissions;
  status: 'active' | 'revoked';
  assignedAt: string;
}

export interface ToolCredentialRequest {
  email: string | null;
  apiToken: string | null;
  accessToken: string | null;
}

export interface ToolConnectionCreateRequest {
  tool: ToolKind;
  name: string;
  baseUrl: string;
  targetResource: string;
  credential: ToolCredentialRequest;
}

export interface ToolConnectionUpdateRequest {
  name: string | null;
  baseUrl: string | null;
  targetResource: string | null;
  credential: ToolCredentialRequest | null;
}

export interface ToolConnectionStatusUpdateRequest {
  status: 'active' | 'paused';
}

export interface ToolConnectionResponse {
  id: string;
  projectId: string;
  tool: ToolKind;
  name: string;
  baseUrl: string;
  targetResource: string;
  credentialMasked: string;
  status: ConnectionStatus;
  lastSyncedAt: string | null;
  lastSyncStatus: SyncJobStatus | null;
  lastSyncError: string | null;
  ingestedCount: number;
  mappingRuleCount: number;
  createdAt: string;
}

export interface ToolConnectionTestRequest {
  tool: ToolKind;
  baseUrl: string;
  targetResource: string;
  credential: ToolCredentialRequest;
}

export interface ToolConnectionTestResponse {
  reachable: boolean;
  resourceName: string;
  detectedItemTypes: string[];
  checkedAt: string;
}

export interface SyncTriggerRequest {
  kind: SyncJobKind;
}

export interface MappingRuleResponse {
  id: string;
  connectionId: string;
  sourceKind: MappingSourceKind;
  sourceValue: string;
  targetEntity: MappingTargetEntity;
  targetWorkProductType: WorkProductType | null;
  statusMap: Record<string, string>;
  enabled: boolean;
}

export interface MappingRuleUpsertRequest {
  sourceKind: MappingSourceKind;
  sourceValue: string;
  targetEntity: MappingTargetEntity;
  targetWorkProductType: WorkProductType | null;
  statusMap: Record<string, string>;
  enabled: boolean;
}

export interface MappingRuleReplaceRequest {
  rules: MappingRuleUpsertRequest[];
  reapply: 'NEXT_POLL' | 'BACKFILL_NOW';
}

export interface SyncJobStats {
  fetched: number;
  upserted: number;
  unmapped: number;
  indexed: number;
  skippedUnchanged: number;
}

export interface SyncJobResponse {
  id: string;
  connectionId: string;
  connectionName: string;
  projectId: string;
  tool: ToolKind;
  kind: SyncJobKind;
  status: SyncJobStatus;
  startedAt: string | null;
  finishedAt: string | null;
  stats: SyncJobStats;
  error: string | null;
  retryable: boolean;
}

export interface EntityStatusUpdateRequest {
  status: string;
  note: string | null;
}

export interface SourceRef {
  tool: ToolKind | 'UPLOAD' | 'MANUAL';
  connectionId: string | null;
  externalId: string | null;
  externalUrl: string | null;
}

export interface RequirementResponse {
  id: string;
  projectId: string;
  code: string;
  title: string;
  priority: Priority;
  status: RequirementStatus;
  assignee: string | null;
  source: SourceRef;
  traceComplete: boolean;
  updatedAt: string;
}

export interface RequirementDetailResponse extends RequirementResponse {
  body: string;
  traceLinks: TraceLinkResponse[];
  history: EntityHistoryResponse[];
}

export interface IssueResponse {
  id: string;
  projectId: string;
  key: string;
  title: string;
  status: IssueStatus;
  severity: Severity | null;
  assignee: string | null;
  resolvedAt: string | null;
  source: SourceRef;
  updatedAt: string;
}

export interface WorkProductResponse {
  id: string;
  projectId: string;
  type: WorkProductType;
  displayName: string;
  title: string | null;
  version: string | null;
  status: WorkProductStatus;
  pmActivity: PmActivity | null;
  siActivity: SiPhase | null;
  applicable: boolean;
  fileUri: string | null;
  externalUrl: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  updatedAt: string;
}

export interface WorkProductChecklistResponse {
  projectId: string;
  approvedCount: number;
  totalCount: number;
  items: WorkProductResponse[];
}

export interface WorkProductVersionResponse {
  id: string;
  version: string;
  status: WorkProductStatus;
  approvedAt: string | null;
  createdAt: string;
}

export interface WorkProductDetailResponse extends WorkProductResponse {
  documentId: string | null;
  chunkCount: number;
  versions: WorkProductVersionResponse[];
  history: EntityHistoryResponse[];
}

export interface WorkProductStatusUpdateRequest {
  status: WorkProductStatus;
  note: string | null;
}

export interface RiskResponse {
  id: string;
  projectId: string;
  title: string;
  probability: Likelihood;
  impact: Likelihood;
  severity: Severity;
  mitigation: string | null;
  status: RiskStatus;
  source: SourceRef;
  updatedAt: string;
}

export interface ChangeRequestResponse {
  id: string;
  projectId: string;
  code: string;
  title: string;
  reason: string;
  impactSummary: string | null;
  status: ChangeRequestStatus;
  source: SourceRef;
  updatedAt: string;
}

export interface CorrectionActionResponse {
  id: string;
  projectId: string;
  code: string;
  finding: string;
  action: string;
  owner: string | null;
  dueDate: string | null;
  status: CorrectionActionStatus;
  overdueDays: number;
  updatedAt: string;
}

export interface TraceLinkResponse {
  id: string;
  projectId: string;
  fromType: TraceEntityType;
  fromId: string;
  fromLabel: string;
  toType: TraceEntityType;
  toId: string;
  toLabel: string;
  linkKind: TraceLinkKind;
  origin: 'auto' | 'manual';
  status: 'active' | 'broken';
  externalUrl: string | null;
  createdAt: string;
}

export interface TraceLinkCreateRequest {
  fromType: TraceEntityType;
  fromId: string;
  toType: TraceEntityType;
  toId: string;
  linkKind: TraceLinkKind;
}

export interface TraceCell {
  targetId: string;
  label: string;
  externalUrl: string | null;
}

export interface TraceabilityRowResponse {
  requirementId: string;
  requirementCode: string;
  requirementTitle: string;
  requirementStatus: RequirementStatus;
  designs: TraceCell[];
  implements: TraceCell[];
  tests: TraceCell[];
  brokenAt: TraceLinkKind[];
}

export interface ProgressRecordResponse {
  id: string;
  projectId: string;
  period: string;
  plannedPct: number;
  actualPct: number;
  summary: string | null;
  source: SourceRef;
}

export interface AcceptanceRecordCreateRequest {
  acceptedBy: string;
  acceptedAt: string;
  conditions: string | null;
  documentId: string | null;
}

export interface AcceptanceRecordResponse {
  id: string;
  projectId: string;
  acceptedBy: string;
  acceptedAt: string;
  conditions: string | null;
  documentUri: string | null;
  status: 'issued' | 'voided';
  createdAt: string;
}

export interface EntityHistoryResponse {
  id: string;
  entityType: string;
  entityId: string;
  field: string;
  fromValue: string | null;
  toValue: string | null;
  actor: string;
  actorName: string | null;
  changedAt: string;
}

export interface DashboardCreateRequest {
  name: string;
  projectId: string | null;
}

export interface DashboardUpdateRequest {
  name: string;
}

export interface DashboardSummaryResponse {
  id: string;
  name: string;
  projectId: string | null;
  projectName: string | null;
  isDefault: boolean;
  widgetCount: number;
  editable: boolean;
  updatedAt: string;
}

export interface GridItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW: number | null;
  minH: number | null;
}

export interface DashboardLayout {
  lg: GridItem[];
  md: GridItem[];
  sm: GridItem[];
}

export interface DashboardLayoutUpdateRequest {
  layout: DashboardLayout;
}

export interface DashboardDetailResponse {
  id: string;
  name: string;
  projectId: string | null;
  projectName: string | null;
  isDefault: boolean;
  editable: boolean;
  layout: DashboardLayout;
  widgets: WidgetResponse[];
  updatedAt: string;
}

export interface WidgetThreshold {
  warn: number;
  critical: number;
}

export interface WidgetOptions {
  unit: string | null;
  sort: 'asc' | 'desc' | null;
  threshold: WidgetThreshold | null;
  stacked: boolean | null;
  showLegend: boolean | null;
  compareWithPrevious: boolean | null;
  columns: string[] | null;
}

export interface WidgetFilter {
  field: string;
  op: FilterOp;
  value: string | number | string[] | number[];
}

export interface WidgetQuery {
  measure: string;
  dimensions: string[];
  filters: WidgetFilter[];
  projectScope: string[];
  limit: number | null;
}

export interface WidgetSpec {
  template: WidgetTemplate;
  title: string;
  query: WidgetQuery;
  options: WidgetOptions;
}

export interface WidgetResponse {
  id: string;
  dashboardId: string;
  template: WidgetTemplate;
  title: string;
  spec: WidgetSpec;
  createdAt: string;
  updatedAt: string;
}

export interface WidgetCreateRequest {
  spec: WidgetSpec;
  gridItem: GridItem | null;
}

export interface WidgetUpdateRequest {
  spec: WidgetSpec;
}

export interface WidgetGenerateRequest {
  prompt: string;
  template: WidgetTemplate | null;
  projectScope: string[];
  dashboardId: string | null;
}

export interface WidgetGenerationRejection {
  reason: string;
  unmatchedTerms: string[];
  suggestedAction: 'ASK_IN_QNA';
  suggestedQuestion: string;
}

export interface WidgetGenerateResponse {
  status: 'GENERATED' | 'NOT_EXPRESSIBLE';
  spec: WidgetSpec | null;
  preview: WidgetDataResponse | null;
  rejection: WidgetGenerationRejection | null;
}

export interface WidgetPreviewRequest {
  spec: WidgetSpec;
}

export interface WidgetDataRequest {
  projectScopeOverride: string[] | null;
  periodOverride: WidgetFilter | null;
}

export interface WidgetColumn {
  key: string;
  label: string;
  type: 'string' | 'number' | 'date' | 'percent' | 'status';
}

export type WidgetRow = Record<string, string | number | null>;

export interface WidgetDataResponse {
  measure: string;
  measureLabel: string;
  unit: string | null;
  dimensions: string[];
  columns: WidgetColumn[];
  rows: WidgetRow[];
  total: WidgetRow | null;
  previousTotal: WidgetRow | null;
  appliedProjectIds: string[];
  truncated: boolean;
  generatedAt: string;
}

export interface SemanticMeasureResponse {
  key: string;
  label: string;
  description: string;
  unit: string | null;
  allowedDimensions: string[];
  allowedFilters: string[];
  defaultTemplates: WidgetTemplate[];
  status: 'active' | 'deprecated';
}

export interface SemanticDimensionResponse {
  key: string;
  label: string;
  description: string;
  valueType: 'string' | 'date' | 'enum';
  enumValues: string[];
  status: 'active' | 'deprecated';
}

export interface SemanticFilterResponse {
  field: string;
  label: string;
  ops: FilterOp[];
  valueType: 'string' | 'number' | 'date' | 'enum';
  enumValues: string[];
  status: 'active' | 'deprecated';
}

export interface SemanticCatalogResponse {
  measures: SemanticMeasureResponse[];
  dimensions: SemanticDimensionResponse[];
  filters: SemanticFilterResponse[];
}

export interface ConversationCreateRequest {
  title: string | null;
  projectScope: string[];
}

export interface ConversationUpdateRequest {
  title: string | null;
  pinned: boolean | null;
  projectScope: string[] | null;
}

export interface ConversationResponse {
  id: string;
  title: string;
  projectScope: string[];
  projectNames: string[];
  pinned: boolean;
  messageCount: number;
  lastMessageAt: string | null;
  createdAt: string;
}

export interface AskRequest {
  question: string;
  projectScope: string[];
}

export interface QueryRouting {
  type: 'DOCUMENT' | 'AGGREGATE' | 'MIXED';
  rewrittenQuery: string;
  measureKey: string | null;
}

export interface MessageSourceResponse {
  footnoteNo: number;
  docChunkId: string;
  sourceType:
    | 'work_product'
    | 'requirement'
    | 'issue'
    | 'risk'
    | 'change_request'
    | 'correction_action';
  sourceId: string;
  sourceLabel: string;
  projectId: string;
  projectName: string;
  tool: ToolKind | 'UPLOAD';
  snippet: string;
  externalUrl: string | null;
  documentUrl: string | null;
  pageNo: number | null;
}

export interface MessageResponse {
  id: string;
  conversationId: string;
  seq: number;
  role: 'user' | 'assistant';
  content: string;
  routing: QueryRouting | null;
  sources: MessageSourceResponse[];
  feedback: 'up' | 'down' | null;
  createdAt: string;
}

export interface MessageFeedbackRequest {
  feedback: 'up' | 'down';
}

export interface SuggestedQuestionsResponse {
  questions: string[];
}

export interface SseStartEvent {
  conversationId: string;
  userMessageId: string;
  assistantMessageId: string;
  routing: QueryRouting;
  retrievedChunkCount: number;
}

export interface SseDeltaEvent {
  text: string;
}

export interface SseSourcesEvent {
  sources: MessageSourceResponse[];
}

export interface SseDoneEvent {
  assistantMessageId: string;
  finishReason: 'stop' | 'no_evidence' | 'length';
  elapsedMs: number;
}

export interface DocumentUploadResponse {
  id: string;
  projectId: string;
  fileName: string;
  fileSize: number;
  mimeType: string;
  status: DocumentStatus;
  uploadedBy: string;
  uploadedAt: string;
  extractedCharCount: number | null;
  draftAvailable: boolean;
  workProductId: string | null;
  error: string | null;
}

export interface DraftRequirement {
  index: number;
  code: string | null;
  title: string;
  body: string;
  priority: Priority;
}

export interface StructuringDraftResponse {
  documentId: string;
  status: 'proposed' | 'confirmed' | 'rejected' | 'manual_override';
  suggestedType: WorkProductType | null;
  rejectedTypeRaw: string | null;
  confidence: number;
  title: string | null;
  version: string | null;
  authoredDate: string | null;
  pmActivity: PmActivity | null;
  siActivity: SiPhase | null;
  requirements: DraftRequirement[];
  createdAt: string;
}

export interface StructuringConfirmRequest {
  type: WorkProductType;
  title: string;
  version: string;
  authoredDate: string | null;
  pmActivity: PmActivity | null;
  siActivity: SiPhase | null;
  requirements: DraftRequirement[];
  workProductStatus: WorkProductStatus;
}

export interface StructuringConfirmResponse {
  workProductId: string;
  createdRequirementIds: string[];
  indexedChunkCount: number;
}
```

`src/standard/iso29110.ts` 는 값과 타입을 같이 내보낸다(런타임 배열이 22종 Select 옵션과 검증에 쓰인다).

```ts
export const WORK_PRODUCT_TYPES = [
  'STATEMENT_OF_WORK', 'PROJECT_PLAN', 'PROGRESS_STATUS_RECORD', 'MEETING_RECORD',
  'CHANGE_REQUEST', 'CORRECTION_REGISTER', 'ACCEPTANCE_RECORD', 'PROJECT_REPOSITORY',
  'REPOSITORY_BACKUP', 'REQUIREMENTS_SPEC', 'TRACEABILITY_RECORD', 'SOFTWARE_DESIGN',
  'TEST_CASES_PROCEDURES', 'SOFTWARE_COMPONENT', 'SOFTWARE', 'TEST_REPORT',
  'PRODUCT_OPERATION_GUIDE', 'SOFTWARE_USER_DOC', 'SOFTWARE_CONFIGURATION',
  'MAINTENANCE_DOC', 'VERIFICATION_RESULTS', 'VALIDATION_RESULTS',
] as const;

export type WorkProductType = (typeof WORK_PRODUCT_TYPES)[number];

export const WORK_PRODUCT_LABEL: Record<WorkProductType, string> = {
  STATEMENT_OF_WORK: '과업지시서',
  PROJECT_PLAN: '사업수행계획서',
  PROGRESS_STATUS_RECORD: '진척 보고',
  MEETING_RECORD: '회의록',
  CHANGE_REQUEST: '변경 요청서',
  CORRECTION_REGISTER: '시정조치 대장',
  ACCEPTANCE_RECORD: '검수확인서',
  PROJECT_REPOSITORY: '사업 저장소',
  REPOSITORY_BACKUP: '저장소 백업',
  REQUIREMENTS_SPEC: '요구사항정의서',
  TRACEABILITY_RECORD: '요구사항추적표',
  SOFTWARE_DESIGN: '설계서',
  TEST_CASES_PROCEDURES: '시험계획서',
  SOFTWARE_COMPONENT: '프로그램 구성요소',
  SOFTWARE: '통합 소프트웨어',
  TEST_REPORT: '시험결과서',
  PRODUCT_OPERATION_GUIDE: '운영지침서',
  SOFTWARE_USER_DOC: '사용자취급설명서',
  SOFTWARE_CONFIGURATION: '소프트웨어 형상',
  MAINTENANCE_DOC: '유지보수문서',
  VERIFICATION_RESULTS: '검토 결과',
  VALIDATION_RESULTS: '확인 결과',
};

export const SI_PHASES = ['SI.1', 'SI.2', 'SI.3', 'SI.4', 'SI.5', 'SI.6'] as const;
export type SiPhase = (typeof SI_PHASES)[number];

export const PM_ACTIVITIES = ['PM.1', 'PM.2', 'PM.3', 'PM.4'] as const;
export type PmActivity = (typeof PM_ACTIVITIES)[number];

export const WORK_PRODUCT_ACTIVITY: Record<WorkProductType, PmActivity | SiPhase> = {
  STATEMENT_OF_WORK: 'PM.1',
  PROJECT_PLAN: 'PM.1',
  PROGRESS_STATUS_RECORD: 'PM.2',
  MEETING_RECORD: 'PM.2',
  CHANGE_REQUEST: 'PM.2',
  CORRECTION_REGISTER: 'PM.3',
  ACCEPTANCE_RECORD: 'PM.4',
  PROJECT_REPOSITORY: 'PM.1',
  REPOSITORY_BACKUP: 'PM.2',
  REQUIREMENTS_SPEC: 'SI.2',
  TRACEABILITY_RECORD: 'SI.2',
  SOFTWARE_DESIGN: 'SI.3',
  TEST_CASES_PROCEDURES: 'SI.3',
  SOFTWARE_COMPONENT: 'SI.4',
  SOFTWARE: 'SI.5',
  TEST_REPORT: 'SI.5',
  PRODUCT_OPERATION_GUIDE: 'SI.5',
  SOFTWARE_USER_DOC: 'SI.5',
  SOFTWARE_CONFIGURATION: 'SI.6',
  MAINTENANCE_DOC: 'SI.6',
  VERIFICATION_RESULTS: 'PM.2',
  VALIDATION_RESULTS: 'SI.5',
};
```

---

## 5. 위젯 렌더러 레지스트리 물리 설계

### 5.1 `features/widgets/widget-types.ts`

```ts
import type { ReactElement } from 'react';
import type { ApiError } from '@/lib/api-error';
import type { WidgetDataResponse, WidgetSpec } from '@/types/api';

export interface WidgetRendererProps {
  spec: WidgetSpec;
  data: WidgetDataResponse;
}

export type WidgetRenderer = (props: WidgetRendererProps) => ReactElement;

export type WidgetViewState =
  | { kind: 'loading' }
  | { kind: 'error'; error: ApiError }
  | { kind: 'empty' }
  | { kind: 'ready'; data: WidgetDataResponse };
```

**8종 렌더러가 모두 같은 props 를 받는다.** 템플릿별 props 를 분기하면 위젯 추가 시 타입·호출부·레지스트리 3곳을 고쳐야 한다(ax-pms 실패 원인). 템플릿별 차이는 `spec.options` 안에 데이터로 있다.

| 템플릿 | 소비하는 필드 | 무시하는 필드 |
| --- | --- | --- |
| `stat-card` | `data.total`, `data.previousTotal`, `options.unit`, `options.threshold`, `options.compareWithPrevious` | `rows` |
| `bar-chart` | `data.rows`, `data.columns`, `data.dimensions[0]`, `options.stacked`, `options.sort`, `options.showLegend` | `total` |
| `line-chart` | `data.rows`, `data.dimensions[0]`(기간축), `options.showLegend` | `total` |
| `pie-chart` | `data.rows`, `data.dimensions[0]`, `options.showLegend` | `total`, `sort` |
| `progress-list` | `data.rows`, `options.unit`, `options.threshold`, `options.sort`, `query.limit` | `total` |
| `data-table` | `data.rows`, `data.columns`, `options.columns`, `options.sort` | `total` |
| `checklist` | `data.rows`, `data.columns`(`status` 타입 컬럼을 Badge 로) | `total` |
| `gantt-summary` | `data.rows`(`plannedPct`/`actualPct`/기간 컬럼) | `total` |

### 5.2 `features/widgets/renderer-registry.ts`

```ts
import type { WidgetTemplate } from '@/types/api';
import type { WidgetRenderer } from './widget-types';
import { StatCardWidget } from './renderers/stat-card-widget';
import { BarChartWidget } from './renderers/bar-chart-widget';
import { LineChartWidget } from './renderers/line-chart-widget';
import { PieChartWidget } from './renderers/pie-chart-widget';
import { ProgressListWidget } from './renderers/progress-list-widget';
import { DataTableWidget } from './renderers/data-table-widget';
import { ChecklistWidget } from './renderers/checklist-widget';
import { GanttSummaryWidget } from './renderers/gantt-summary-widget';
import { UnsupportedWidget } from './renderers/unsupported-widget';

export const widgetRenderers: Record<WidgetTemplate, WidgetRenderer> = {
  'stat-card': StatCardWidget,
  'bar-chart': BarChartWidget,
  'line-chart': LineChartWidget,
  'pie-chart': PieChartWidget,
  'progress-list': ProgressListWidget,
  'data-table': DataTableWidget,
  checklist: ChecklistWidget,
  'gantt-summary': GanttSummaryWidget,
};

export const resolveWidgetRenderer = (template: string): WidgetRenderer =>
  widgetRenderers[template as WidgetTemplate] ?? UnsupportedWidget;
```

`resolveWidgetRenderer` 의 인자가 `string` 인 것이 핵심이다. `template` 은 서버 DB 의 `widget.spec_json` 에서 오는 **데이터**이고, 프론트가 아직 모르는 값이 올 수 있다. `WidgetTemplate` 으로 좁혀 받으면 그 사실이 타입 시스템에 가려지고 런타임에 `undefined` 컴포넌트로 화면 전체가 죽는다.

`UnsupportedWidget` 은 `WidgetRendererProps` 를 받되 데이터를 렌더하지 않고 Alert 를 그린다:

```
⚠ 지원하지 않는 위젯 유형입니다: {spec.template}
   이 위젯을 삭제하거나 지원되는 템플릿으로 다시 만드세요.
```

### 5.3 `features/widgets/widget-frame.tsx` — 공통 프레임

```ts
export interface WidgetFrameProps {
  title: string;
  subtitle: string | null;
  state: WidgetViewState;
  editing: boolean;
  onRefresh: () => void;
  onEdit: () => void;
  onDelete: () => void;
  children: (data: WidgetDataResponse) => ReactNode;
}

export const WidgetFrame: (props: WidgetFrameProps) => ReactElement;
```

| 영역 | 구성 | 상태별 동작 |
| --- | --- | --- |
| 헤더 | `CardHeader` + `CardTitle`(title) + `CardDescription`(subtitle = `measureLabel` · 적용 프로젝트 수) | 항상 |
| 드래그 핸들 | 헤더 전체에 `className="widget-drag-handle"`. 편집 모드에서만 `cursor-grab` | `editing=true` 일 때만 rgl 이 반응 |
| 툴바 | `CardAction` 슬롯. 조회모드: 새로고침 버튼 1개. 편집모드: `DropdownMenu`(편집·삭제) | `editing` 분기 |
| 우클릭 | `ContextMenu` 로 툴바와 동일 항목 | 편집 모드만 |
| loading | 본문에 `Skeleton` (헤더는 유지) | — |
| error | `Alert variant="destructive"` + `error.body.message` + 재시도 버튼. **403 은 "이 프로젝트의 대시보드 열람 권한이 없습니다"로 치환** | — |
| empty | `rows.length === 0 && total === null` → "조건에 맞는 데이터가 없습니다" + 적용 범위 표시 | — |
| ready | `children(data)` 호출 | — |
| 잘림 표시 | `data.truncated === true` 이면 푸터에 "상위 {limit}건만 표시" Badge | ready 일 때 |

`children` 을 렌더 프롭으로 둔 이유: `state.kind === 'ready'` 일 때만 `data` 가 존재한다는 사실을 타입으로 전달하기 위해서다. 렌더러가 `data | null` 을 받으면 8곳에서 null 분기를 반복한다.

### 5.4 `features/widgets/widget-data.ts` — 파생 유틸

```ts
export interface Series {
  key: string;
  label: string;
  color: string;
}

export const resolveColumns: (
  data: WidgetDataResponse,
  options: WidgetOptions,
) => WidgetColumn[];

export const toSeries: (data: WidgetDataResponse) => Series[];

export const toChartConfig: (series: Series[]) => ChartConfig;

export const pickTotal: (
  data: WidgetDataResponse,
) => { value: number | null; column: WidgetColumn | null };

export const pickDelta: (
  data: WidgetDataResponse,
) => { diff: number; ratio: number; direction: 'up' | 'down' | 'flat' } | null;
```

| 함수 | 규칙 |
| --- | --- |
| `resolveColumns` | `options.columns` 가 `null` 이면 `data.columns` 전부. 아니면 그 순서대로 필터(카탈로그에 없는 키는 조용히 제외) |
| `toSeries` | `data.columns` 중 `type === 'number' \| 'percent'` 인 것을 시리즈로, `--chart-1..8` 을 순환 배정 |
| `toChartConfig` | shadcn `ChartConfig` 형태 `{ [key]: { label, color: 'var(--chart-n)' } }` |
| `pickTotal` | `data.total` 의 첫 숫자 컬럼 값. `total` 이 `null` 이면 `rows[0]` 의 첫 숫자 컬럼 |
| `pickDelta` | `previousTotal` 이 `null` 이면 `null`. `prev === 0` 이면 `ratio = 0`, `direction` 은 `diff` 부호. 0 나눗셈을 만들지 않는다 |

### 5.5 `features/dashboard/dashboard-grid.tsx` — react-grid-layout v2 통합

v2 는 v1 과 API 가 다르다. `WidthProvider` HOC 가 없어졌고 `useContainerWidth` 훅 + `width` prop, 그리고 `isDraggable`/`isResizable`/`draggableHandle` 이 `dragConfig`/`resizeConfig` 객체로 이동했다.

```ts
export interface DashboardGridProps {
  layouts: DashboardLayout;
  editing: boolean;
  onLayoutChange: (layout: DashboardLayout) => void;
  children: ReactNode;
}

export const DashboardGrid: (props: DashboardGridProps) => ReactElement;
```

내부 구성 확정값:

| prop | 값 | 근거 |
| --- | --- | --- |
| 컴포넌트 | `ResponsiveGridLayout` (`react-grid-layout` 최상위 export) | v2 규격 |
| `width` | `useContainerWidth({ initialWidth: 1280 })` 의 `width`, `containerRef` 를 감싸는 div 에 부착 | v2 는 `width` 가 필수 prop |
| `breakpoints` | `{ lg: 1200, md: 996, sm: 0 }` | `DashboardLayout` 의 3키와 1:1 |
| `cols` | `{ lg: 12, md: 8, sm: 4 }` | PRD 4.3.1 "12컬럼" |
| `rowHeight` | `80` | PRD 4.3.1 |
| `margin` | `[16, 16]` | 토큰 `--spacing` 4배 |
| `containerPadding` | `[0, 0]` | 페이지 패딩이 이미 있다 |
| `layouts` | `toGridLayouts(layouts)` | §5.7 변환 |
| `dragConfig` | `{ enabled: editing, handle: '.widget-drag-handle', threshold: 4 }` | 편집 모드에서만, 헤더로만 드래그 |
| `resizeConfig` | `{ enabled: editing, handles: ['se'] }` | 우하단 1핸들 |
| `compactor` | 기본값(`verticalCompactor`) | 빈 공간 자동 정리 |
| `onLayoutChange` | `(_, all) => onLayoutChange(toDashboardLayout(all))` — **`editing === false` 이면 호출을 무시** | 조회 모드에서 브레이크포인트 전환만으로 서버에 저장 요청이 나가는 것을 막는다 |
| CSS | `main.tsx` 에서 `import 'react-grid-layout/css/styles.css'` 1줄 | v2 의 css 에 resize 핸들 스타일이 포함되어 있어 `react-resizable/css/styles.css` 추가 import 는 불필요 |

각 자식은 `<div key={widget.id}>` 로 감싸고 그 안에 `WidgetHost` 를 둔다. rgl 은 자식의 `key` 로 `layout.i` 를 찾는다.

### 5.6 `features/dashboard/use-dashboard-editor.ts` — 편집 상태 기계

```ts
export interface DashboardEditorState {
  editing: boolean;
  dirty: boolean;
  layout: DashboardLayout;
  saving: boolean;
  beginEdit: () => void;
  changeLayout: (next: DashboardLayout) => void;
  save: () => Promise<void>;
  cancel: () => void;
}

export const useDashboardEditor: (
  dashboard: DashboardDetailResponse,
  onSaved: (next: DashboardDetailResponse) => void,
) => DashboardEditorState;
```

```
       beginEdit                changeLayout*              save (PUT layout)
view ────────────► edit(clean) ──────────────► edit(dirty) ─────────────► view
  ▲                    │                            │                        
  └────────────────────┴──── cancel (서버 값으로 원복) ┘
```

| 규칙 | 구현 |
| --- | --- |
| 단일 원천 | `layout` 초기값은 `dashboard.layout` 뿐이다. `localStorage` 를 읽지 않는다(INV-27, eslint 로 차단) |
| 취소 | `setLayout(dashboard.layout)` + `setEditing(false)`. 별도 백업 변수를 두지 않는다 |
| 저장 | `replaceDashboardLayout(dashboard.id, { layout })` → 응답 `DashboardDetailResponse` 를 `onSaved` 로 올려 페이지 상태를 교체 |
| 이탈 경고 | `dirty && editing` 일 때 `beforeunload` 리스너 등록. 라우터 내 이동은 경고하지 않는다(과설계) |
| 위젯 추가 | 마법사가 `WidgetCreateRequest.gridItem` 에 `defaultGridItem(template, currentLayout)` 을 실어 보낸다. 서버 응답 후 대시보드를 재조회한다 — 클라이언트가 레이아웃을 낙관적으로 계산해 두 원천을 만들지 않는다 |
| 편집 진입 조건 | `dashboard.editable === true` 일 때만 `beginEdit` 노출. 역할 판정은 서버 값을 그대로 쓴다 |

### 5.7 `features/dashboard/layout-mapper.ts`

```ts
import type { Layout, ResponsiveLayouts } from 'react-grid-layout';
import type { DashboardLayout, GridItem, WidgetTemplate } from '@/types/api';

export type Breakpoint = 'lg' | 'md' | 'sm';

export const toGridLayouts: (layout: DashboardLayout) => ResponsiveLayouts<Breakpoint>;
export const toDashboardLayout: (layouts: ResponsiveLayouts<Breakpoint>) => DashboardLayout;
export const defaultGridItem: (template: WidgetTemplate, current: GridItem[]) => GridItem;
```

| 함수 | 변환 규칙 |
| --- | --- |
| `toGridLayouts` | `GridItem.minW/minH` 의 `null` → `undefined`. rgl 의 `LayoutItem` 은 optional(`minW?: number`) 이고 우리 DTO 는 `number \| null` 이다. **`exactOptionalPropertyTypes` 때문에 이 변환을 생략할 수 없다** |
| `toDashboardLayout` | 역변환(`undefined` → `null`). rgl 이 반환하는 여분 필드(`static`, `moved`, `isDraggable` …)는 **버린다**. `i/x/y/w/h/minW/minH` 7키만 남겨 서버 계약과 일치시킨다 |
| `defaultGridItem` | `WIDGET_TEMPLATES[template].defaultSize` (`{w,h,minW,minH}`) 를 쓰고, `y` 는 `Math.max(...current.map(g => g.y + g.h), 0)`, `x = 0` |

`defaultSize` 확정값 (`template-catalog.ts`):

| template | w | h | minW | minH |
| --- | --- | --- | --- | --- |
| `stat-card` | 3 | 2 | 2 | 2 |
| `bar-chart` | 6 | 4 | 3 | 3 |
| `line-chart` | 6 | 4 | 3 | 3 |
| `pie-chart` | 4 | 4 | 3 | 3 |
| `progress-list` | 4 | 4 | 3 | 3 |
| `data-table` | 8 | 5 | 4 | 3 |
| `checklist` | 6 | 6 | 4 | 4 |
| `gantt-summary` | 12 | 4 | 6 | 3 |

---

## 6. SSE 소비 물리 설계

### 6.1 `lib/http.ts` — `openStream`

```ts
export interface StreamOptions {
  body: unknown;
  signal: AbortSignal;
}

export const openStream: (
  path: string,
  options: StreamOptions,
) => Promise<ReadableStream<Uint8Array>>;
```

| 단계 | 동작 |
| --- | --- |
| 1 | `fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', Authorization: 'Bearer ' + token }, body: JSON.stringify(body), signal })` |
| 2 | `res.ok === false` → 본문을 JSON 으로 읽어 `ApiError` throw. **스트림을 열기 전에 실패하는 403/503 은 일반 에러와 같은 경로로 처리한다** |
| 3 | 401 이면 `request` 와 동일한 단일비행 refresh 를 1회 시도 후 재요청. 두 번째도 401 이면 `onUnauthorized()` 호출 |
| 4 | `res.body === null` → `ApiError(0, {code:'INTERNAL_ERROR', ...})` |
| 5 | `res.body` 반환 |

`EventSource` 를 쓰지 않는 이유는 `02-logical-api.md` §4.1 에 확정되어 있다(POST·인증 헤더 불가).

### 6.2 `lib/sse.ts` — 파서

```ts
export interface SseEvent {
  event: string;
  data: string;
}

export const parseSseStream: (
  body: ReadableStream<Uint8Array>,
) => AsyncGenerator<SseEvent, void, undefined>;
```

동작 규격:

| # | 규칙 |
| --- | --- |
| P1 | `TextDecoderStream` 대신 `TextDecoder('utf-8')` + `{ stream: true }` 로 직접 디코드한다. **한글이 청크 경계에서 잘려도 깨지지 않는다.** jsdom 에 `TextDecoderStream` 이 없어 테스트에서도 이 방식만 동작한다 |
| P2 | 내부 버퍼에 누적하고 `\n\n` 를 이벤트 구분자로 삼는다. `\r\n\r\n` 도 같은 구분자로 처리한다 |
| P3 | 블록 안에서 `event:` 로 시작하는 줄이 `event` 필드, `data:` 로 시작하는 줄이 `data` 필드. `data:` 가 여러 줄이면 `\n` 으로 이어 붙인다(SSE 표준) |
| P4 | `:` 뒤 선행 공백 1개만 제거한다. 2개째부터는 데이터다 |
| P5 | `event` 가 없으면 `'message'` 로 채운다 |
| P6 | `:` 로 시작하는 줄(주석)과 `id:`/`retry:` 는 무시한다 |
| P7 | 스트림 종료 시 남은 버퍼가 완전한 블록이면 마지막으로 1건 방출하고, 아니면 버린다 |
| P8 | `finally` 에서 `reader.releaseLock()` 을 호출한다. abort 시 리더가 잠긴 채 남지 않게 한다 |
| P9 | `AbortError` 는 다시 throw 하지 않고 제너레이터를 정상 종료시킨다. 중지는 오류가 아니다 |

### 6.3 `hooks/use-ask-stream.ts` — 상태 기계

```ts
export type AskPhase = 'idle' | 'streaming' | 'finalizing' | 'aborted' | 'error';

export interface AskStreamState {
  phase: AskPhase;
  routing: QueryRouting | null;
  draftText: string;
  sources: MessageSourceResponse[];
  assistantMessageId: string | null;
  finishReason: SseDoneEvent['finishReason'] | null;
  error: ApiError | null;
  ask: (conversationId: string, request: AskRequest) => Promise<void>;
  abort: () => void;
  reset: () => void;
}

export const useAskStream: (onSettled: (conversationId: string) => void) => AskStreamState;
```

이벤트 처리표:

| event | 처리 |
| --- | --- |
| `ping` | 무시 |
| `start` | `phase='streaming'`, `routing`, `assistantMessageId` 저장. `retrievedChunkCount === 0` 이면 UI 에 "근거 없음" 톤 적용 |
| `delta` | `draftText += data.text` (setState 함수형 갱신) |
| `sources` | `sources = data.sources` |
| `done` | `phase='finalizing'`, `finishReason` 저장 → `onSettled(conversationId)` 호출 |
| `error` | 데이터가 `ErrorResponse` 다. `ApiError` 로 감싸 `phase='error'` |
| 알 수 없는 event | 무시. 서버가 새 이벤트를 추가해도 클라이언트가 죽지 않는다 |

| 항목 | 확정 |
| --- | --- |
| 중지 | `abort()` → `controllerRef.current.abort()` → 제너레이터 정상 종료 → `phase='aborted'`. `draftText` 는 지우지 않고 화면에 "중지됨" Badge 를 붙인다(`02-logical-api.md` §4.4) |
| 최종본 | `done` 수신 후 `draftText` 를 최종본으로 쓰지 않는다. `onSettled` 가 `listMessages(conversationId)` 를 재조회하고, 그 결과가 스레드에 반영되면 `reset()` 으로 draft 를 비운다. **각주 제거로 본문이 바뀌기 때문**(INV-31) |
| 부분 렌더 | `draftText` 는 `AnswerBody` 로 그대로 렌더한다. 각주 링크는 `sources` 가 비어 있는 동안 비활성(hover 없음) 상태로 그린다 |
| 재진입 방지 | `phase === 'streaming'` 인 동안 `ask()` 재호출을 무시한다. 전송 버튼은 중지 버튼으로 교체된다 |
| 언마운트 | `useEffect` cleanup 에서 `abort()` |
| 타임아웃 | 클라이언트 타임아웃을 걸지 않는다. 서버 `SseEmitter` 가 190초에 닫으면 스트림 종료로 감지된다 |

### 6.4 `features/ax-query/answer-body.tsx` — 각주 파싱

```ts
export interface FootnoteSegment {
  kind: 'text' | 'footnote';
  value: string;
  footnoteNo: number | null;
}

export const parseFootnotes: (content: string) => FootnoteSegment[];
```

`/\[(\d{1,2})\]/g` 로 분할한다. `sources` 에 대응 `footnoteNo` 가 없는 각주는 **텍스트로 렌더**한다(서버가 이미 제거했어야 하지만, 스트리밍 중간 상태에서는 아직 `sources` 가 오지 않았으므로 링크로 만들 수 없다).

---

## 7. 테스트 물리 전략

### 7.1 원칙

| 항목 | 결정 |
| --- | --- |
| 러너 | `vitest` (Vite 설정을 그대로 공유해 alias `@` 가 자동 적용된다. Jest 를 쓰면 moduleNameMapper 를 이중 관리해야 한다) |
| 환경 | `jsdom`. 브라우저 러너(playwright)는 도입하지 않는다 |
| 네트워크 | `globalThis.fetch = vi.fn()`. MSW 도입 금지(§0) |
| 범위 | **로직이 있는 곳만 테스트한다.** `components/ui/**` 는 shadcn 소스 그대로이므로 커버리지에서 제외한다. 순수 표시용 컴포넌트도 테스트하지 않는다 |
| 렌더 테스트 기준 | 접근성 쿼리(`getByRole`, `getByLabelText`) 우선. `data-testid` 는 쓰지 않는다 |

### 7.2 대상과 검증 항목

| # | 대상 | 검증 |
| --- | --- | --- |
| T1 | `lib/sse.ts` `parseSseStream` | ① `event:`/`data:` 정상 파싱 ② `data:` 다줄 결합 ③ **한 이벤트가 2개 청크에 걸쳐 도착해도 1건으로 복원** ④ UTF-8 한글이 청크 경계에서 잘려도 깨지지 않음 ⑤ `ping`·주석 줄 무시 ⑥ 미완성 꼬리 버퍼 폐기 |
| T2 | `lib/http.ts` `request` | ① 200 JSON 반환 ② 204 는 `undefined` ③ 4xx 는 `ApiError` throw + `code` 보존 ④ **401 → refresh 1회 → 원요청 재시도 성공** ⑤ refresh 도 401 이면 `onUnauthorized` 1회 호출 ⑥ **동시 3요청이 401 을 받아도 refresh 는 1회만**(단일비행) ⑦ 빈 바디 4xx 도 `ApiError` 로 승격 |
| T3 | `features/widgets/renderer-registry.ts` | ① 8종이 각각 지정 렌더러로 해석됨 ② 미지원 문자열(`'sunburst'`)이 `UnsupportedWidget` 으로 해석됨 ③ `Object.keys(widgetRenderers)` 가 `WidgetTemplate` 8종과 정확히 일치(누락·오타 검출) |
| T4 | `features/widgets/widget-data.ts` | ① `resolveColumns` 가 `options.columns` 순서를 따르고 미존재 키를 제외 ② `pickDelta` 가 `previousTotal=null` 이면 `null` ③ **`previousTotal=0` 에서 0 나눗셈이 나지 않음** ④ `toSeries` 가 숫자·퍼센트 컬럼만 고름 |
| T5 | `features/dashboard/layout-mapper.ts` | ① `null` minW/minH 가 `undefined` 로 변환 ② 역변환에서 `undefined` 가 `null` 로 복원 ③ rgl 여분 필드(`static`, `moved`)가 제거됨 ④ 왕복 변환이 원본과 동일(idempotent) |
| T6 | `features/auth/guards.tsx` | ① 미인증 → `/login` 리다이렉트 + `state.from` 보존 ② `booting` 중에는 리다이렉트하지 않고 스켈레톤 ③ `RequireRole` 이 허용 밖 역할을 `/403` 으로 ④ **`RequireProject` 가 `allowedProjectIds` 밖 `:projectId` 를 `/403` 으로** |
| T7 | `features/projects/project-form.tsx` | ① 필수 4필드 누락 시 제출 차단 + 필드 메시지 ② `endDate < startDate` 거부(INV-08) ③ 서버 400 `fieldErrors` 가 해당 필드 메시지로 매핑됨 ④ 정상 입력 시 `ProjectCreateRequest` 형태 그대로 제출 |
| T8 | `standard/iso29110.ts` | ① `WORK_PRODUCT_TYPES.length === 22` ② `WORK_PRODUCT_LABEL`·`WORK_PRODUCT_ACTIVITY` 키가 22종과 정확히 일치 ③ 중복 없음. **백엔드 enum 과의 값 일치는 백엔드 계약 테스트가 담당한다**(INV-18) |
| T9 | `lib/format.ts` | ① `formatDate` 가 `2026-03-01` → `2026. 3. 1.` ② `formatDateTime` 이 UTC ISO 를 로컬로 변환 ③ `formatPercent` 소수 처리 ④ 잘못된 입력에 throw 하지 않고 원문 반환 |

### 7.3 테스트 파일 경로 (9)

소스 옆에 둔다. `__tests__` 디렉터리를 만들지 않는다 — 파일 하나 옮길 때 두 곳을 고치게 된다.

```
src/lib/sse.test.ts
src/lib/http.test.ts
src/lib/format.test.ts
src/standard/iso29110.test.ts
src/features/widgets/renderer-registry.test.tsx
src/features/widgets/widget-data.test.ts
src/features/dashboard/layout-mapper.test.ts
src/features/auth/guards.test.tsx
src/features/projects/project-form.test.tsx
```

### 7.4 SSE 테스트용 스트림 생성 (테스트 파일 안에 두는 헬퍼)

```ts
const streamOf = (...chunks: string[]): ReadableStream<Uint8Array> => {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
};
```

`streamOf('event: delta\ndata: {"text":"3월 기준 ', '요구사항"}\n\n')` 처럼 **의도적으로 경계를 어긋나게** 넣어 T1-③ 을 검증한다.

---

## 8. 디자인 토큰 최종안 (`src/index.css`)

### 8.1 팔레트 결정

| 항목 | 값 | 근거 |
| --- | --- | --- |
| 기준 | shadcn `baseColor: slate` + oklch 표기 | Tailwind v4 / shadcn 기본 규격 |
| primary 색상 | 청색 계열 `oklch(0.52 0.17 258)` | 발주사 관리 도구. 상태 색(성공 녹색·경고 황색·위험 적색)과 색상환에서 충분히 떨어져 있어 배지와 버튼이 섞이지 않는다 |
| radius | `0.625rem` | shadcn 기본 |
| 상태 색 | `--success`/`--warning`/`--info` 를 **별도 토큰으로 추가**한다 | 산출물 4상태·동기화 5상태·추적 끊김 표시가 `primary`/`destructive` 2색으로 표현되지 않는다. 컴포넌트마다 `text-green-600` 을 직접 쓰면 다크 모드에서 대비가 깨진다 |
| 차트 색 | `--chart-1` ~ `--chart-8` | shadcn 기본은 5개다. 매핑 규칙·용역사·산출물 유형 차원이 5개를 넘는다 |

### 8.2 `src/index.css` 전문

```css
@import 'tailwindcss';
@import 'tw-animate-css';

@custom-variant dark (&:where(.dark, .dark *));

:root {
  --radius: 0.625rem;

  --background: oklch(1 0 0);
  --foreground: oklch(0.21 0.02 260);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.21 0.02 260);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.21 0.02 260);
  --primary: oklch(0.52 0.17 258);
  --primary-foreground: oklch(0.98 0.005 258);
  --secondary: oklch(0.968 0.005 260);
  --secondary-foreground: oklch(0.29 0.02 260);
  --muted: oklch(0.968 0.005 260);
  --muted-foreground: oklch(0.55 0.016 260);
  --accent: oklch(0.955 0.012 258);
  --accent-foreground: oklch(0.29 0.02 260);
  --destructive: oklch(0.58 0.21 27);
  --destructive-foreground: oklch(0.985 0.008 27);
  --success: oklch(0.62 0.14 155);
  --success-foreground: oklch(0.985 0.01 155);
  --warning: oklch(0.72 0.16 75);
  --warning-foreground: oklch(0.24 0.04 75);
  --info: oklch(0.60 0.13 235);
  --info-foreground: oklch(0.985 0.008 235);
  --border: oklch(0.922 0.006 260);
  --input: oklch(0.922 0.006 260);
  --ring: oklch(0.52 0.17 258);

  --chart-1: oklch(0.62 0.17 258);
  --chart-2: oklch(0.66 0.14 185);
  --chart-3: oklch(0.66 0.15 155);
  --chart-4: oklch(0.76 0.15 85);
  --chart-5: oklch(0.68 0.18 45);
  --chart-6: oklch(0.62 0.19 20);
  --chart-7: oklch(0.58 0.19 315);
  --chart-8: oklch(0.60 0.16 285);

  --sidebar: oklch(0.984 0.003 260);
  --sidebar-foreground: oklch(0.21 0.02 260);
  --sidebar-primary: oklch(0.52 0.17 258);
  --sidebar-primary-foreground: oklch(0.98 0.005 258);
  --sidebar-accent: oklch(0.955 0.012 258);
  --sidebar-accent-foreground: oklch(0.29 0.02 260);
  --sidebar-border: oklch(0.922 0.006 260);
  --sidebar-ring: oklch(0.52 0.17 258);
}

.dark {
  --background: oklch(0.16 0.014 262);
  --foreground: oklch(0.97 0.004 260);
  --card: oklch(0.21 0.017 262);
  --card-foreground: oklch(0.97 0.004 260);
  --popover: oklch(0.21 0.017 262);
  --popover-foreground: oklch(0.97 0.004 260);
  --primary: oklch(0.70 0.15 258);
  --primary-foreground: oklch(0.19 0.03 258);
  --secondary: oklch(0.27 0.018 262);
  --secondary-foreground: oklch(0.97 0.004 260);
  --muted: oklch(0.27 0.018 262);
  --muted-foreground: oklch(0.71 0.014 260);
  --accent: oklch(0.30 0.028 258);
  --accent-foreground: oklch(0.97 0.004 260);
  --destructive: oklch(0.68 0.19 24);
  --destructive-foreground: oklch(0.17 0.03 24);
  --success: oklch(0.72 0.15 155);
  --success-foreground: oklch(0.17 0.03 155);
  --warning: oklch(0.80 0.15 78);
  --warning-foreground: oklch(0.20 0.04 78);
  --info: oklch(0.72 0.13 235);
  --info-foreground: oklch(0.17 0.03 235);
  --border: oklch(1 0 0 / 12%);
  --input: oklch(1 0 0 / 16%);
  --ring: oklch(0.60 0.15 258);

  --chart-1: oklch(0.66 0.18 258);
  --chart-2: oklch(0.72 0.14 185);
  --chart-3: oklch(0.72 0.15 155);
  --chart-4: oklch(0.80 0.15 85);
  --chart-5: oklch(0.72 0.18 45);
  --chart-6: oklch(0.68 0.19 20);
  --chart-7: oklch(0.66 0.18 315);
  --chart-8: oklch(0.68 0.16 285);

  --sidebar: oklch(0.21 0.017 262);
  --sidebar-foreground: oklch(0.97 0.004 260);
  --sidebar-primary: oklch(0.70 0.15 258);
  --sidebar-primary-foreground: oklch(0.19 0.03 258);
  --sidebar-accent: oklch(0.30 0.028 258);
  --sidebar-accent-foreground: oklch(0.97 0.004 260);
  --sidebar-border: oklch(1 0 0 / 12%);
  --sidebar-ring: oklch(0.60 0.15 258);
}

@theme inline {
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);

  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-success: var(--success);
  --color-success-foreground: var(--success-foreground);
  --color-warning: var(--warning);
  --color-warning-foreground: var(--warning-foreground);
  --color-info: var(--info);
  --color-info-foreground: var(--info-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);

  --color-chart-1: var(--chart-1);
  --color-chart-2: var(--chart-2);
  --color-chart-3: var(--chart-3);
  --color-chart-4: var(--chart-4);
  --color-chart-5: var(--chart-5);
  --color-chart-6: var(--chart-6);
  --color-chart-7: var(--chart-7);
  --color-chart-8: var(--chart-8);

  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-border: var(--sidebar-border);
  --color-sidebar-ring: var(--sidebar-ring);

  --font-sans:
    'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont, system-ui,
    'Segoe UI', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
  --font-mono:
    ui-monospace, 'SFMono-Regular', 'JetBrains Mono', Menlo, Consolas, monospace;
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground;
    font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
    -webkit-font-smoothing: antialiased;
  }
  .tabular {
    font-variant-numeric: tabular-nums;
  }
}

@layer components {
  .react-grid-item.react-grid-placeholder {
    @apply rounded-lg bg-primary/15;
  }
  .react-grid-item > .react-resizable-handle::after {
    @apply border-muted-foreground/60;
  }
}
```

`--font-sans` 는 Pretendard 를 **우선순위 1번으로만** 두고 폰트 파일을 번들하거나 CDN 을 참조하지 않는다. 설치되어 있으면 쓰고 없으면 시스템 한글 폰트로 떨어진다. 웹폰트 다운로드는 로컬 구동 제약(§환경)과 초기 렌더 비용 양쪽에서 이득이 없다.

### 8.3 상태 색 매핑 (`standard/labels.ts`)

`StatusBadge` 는 아래 표만 참조한다. 컴포넌트 안에서 색을 직접 고르지 않는다.

| 도메인 | 값 | 라벨 | 톤 |
| --- | --- | --- | --- |
| `ProjectStatus` | `planning` / `active` / `closing` / `closed` | 준비 / 진행 / 종료중 / 종료 | `neutral` / `info` / `warning` / `muted` |
| `WorkProductStatus` | `none` / `draft` / `submitted` / `approved` / `rejected` | 없음 / 작성중 / 제출 / 승인 / 반려 | `muted` / `neutral` / `info` / `success` / `destructive` |
| `SyncJobStatus` | `queued` / `running` / `succeeded` / `failed` / `cancelled` | 대기 / 실행중 / 성공 / 실패 / 취소 | `neutral` / `info` / `success` / `destructive` / `muted` |
| `ConnectionStatus` | `draft` / `verified` / `active` / `paused` / `failed` | 임시 / 검증됨 / 활성 / 일시중지 / 실패 | `muted` / `info` / `success` / `warning` / `destructive` |
| `RequirementStatus` | `defined` … `accepted` / `rejected` | 정의 / 설계 / 구현 / 검증 / 인수 / 반려 | `neutral` ×4 → `success` / `destructive` |
| `IssueStatus` | `open` / `in_progress` / `resolved` / `closed` | 열림 / 진행 / 해결 / 종료 | `warning` / `info` / `success` / `muted` |
| `RiskStatus` | `open` / `mitigating` / `closed` | 열림 / 완화중 / 종료 | `destructive` / `warning` / `muted` |
| `ChangeRequestStatus` | `requested` … `applied` | 요청 / 검토 / 승인 / 반려 / 반영 | `neutral` / `info` / `success` / `destructive` / `success` |
| `CorrectionActionStatus` | `open` / `done` / `overdue` | 열림 / 완료 / 지연 | `warning` / `success` / `destructive` |
| `Severity` | `critical` / `high` / `medium` / `low` | 심각 / 높음 / 보통 / 낮음 | `destructive` / `warning` / `neutral` / `muted` |
| `Priority` | `MUST` / `SHOULD` / `COULD` / `WONT` | 필수 / 권장 / 선택 / 제외 | `destructive` / `warning` / `neutral` / `muted` |
| 추적 상태 | `brokenAt.length > 0` | 추적 끊김 | `destructive` |

톤 → Badge variant/클래스:

| 톤 | 클래스 |
| --- | --- |
| `neutral` | `variant="secondary"` |
| `muted` | `variant="outline" text-muted-foreground` |
| `info` | `bg-info/12 text-info border-info/30` |
| `success` | `bg-success/12 text-success border-success/30` |
| `warning` | `bg-warning/15 text-warning-foreground border-warning/40` (라이트에서 황색 위 흰 글씨 대비 미달을 피한다) |
| `destructive` | `variant="destructive"` |

### 8.4 타이포·간격·모션

| 항목 | 값 |
| --- | --- |
| 본문 | `text-sm` (14px) 기준. 화면 밀도가 높은 관리 도구다 |
| 페이지 제목 | `text-xl font-semibold tracking-tight` |
| 섹션 제목 | `text-base font-semibold` |
| 지표 숫자 | `text-3xl font-semibold tabular` (`.tabular` = `tabular-nums`, PRD §6.2) |
| 테이블 셀 | `py-2 text-sm`, 숫자 컬럼은 `text-right tabular` |
| 페이지 패딩 | `p-6`, 카드 간격 `gap-4` |
| 위젯 그리드 | rowHeight 80 / margin 16 (§5.5) |
| 모션 | `tw-animate-css` 의 `animate-in`/`fade-in-0`/`zoom-in-95` 기본값만. 커스텀 keyframes 를 만들지 않는다 |
| 다크 모드 전환 | `<html class="light">` ↔ `"dark"` 토글. **1차 릴리스에서는 토글 UI 를 만들지 않는다.** 토큰만 준비하고 `light` 고정 |

---

## 9. 다음 단계로 넘기는 항목

| 항목 | 후속 |
| --- | --- |
| `semantic_measure` 초기 행·라벨(마법사 2단계 선택지 원문) | `05-semantic-catalog` |
| Q&A 시스템 프롬프트·청킹 파라미터 | `05-ai-pipeline` |
| 백엔드 enum ↔ `standard/iso29110.ts` 값 일치 계약 테스트 | `03-physical-backend` |
| 실제 화면 시각 설계(목업) | `design-for-ai` 워크플로 `plan → mock → build` |
