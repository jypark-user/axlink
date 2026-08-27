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
    extends: [
      js.configs.recommended,
      // 타입 정보를 쓰는 규칙까지 켠다 — 떠 있는 Promise 나 잘못 넘긴 async 콜백은
      // 타입을 봐야만 잡힌다. 느리지만 이게 린터를 두는 이유다.
      ...tseslint.configs.recommendedTypeChecked,
      // 이 플러그인은 configs['recommended-latest'] 가 아직 구형(배열) 모양이다 — flat 쪽을 쓴다.
      reactHooks.configs.flat['recommended-latest'],
      reactRefresh.configs.vite,
      // 포맷은 prettier 가 맡는다 — 겹치는 규칙을 꺼서 둘이 싸우지 않게 한다. 항상 맨 뒤.
      prettier,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      /*
       * JSX 속성(onClick 등)에 async 함수를 주는 것은 React 관용이다 — 여기서는 끈다.
       * 대신 함수 인자로 Promise 가 넘어가는 경우(setInterval(async…), 콜백 등)는 그대로 잡는다.
       * 그쪽은 반환값이 버려져 실패가 조용히 사라지는 진짜 위험이다.
       */
      '@typescript-eslint/no-misused-promises': [
        'error',
        { checksVoidReturn: { attributes: false } },
      ],
      // 안 쓰는 값은 지운다. 다만 `_` 로 시작하면 일부러 받은 것으로 본다.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],
    },
  },
  {
    /*
     * React Compiler 계열 신규 규칙. 이 프로젝트는 컴파일러를 쓰지 않으므로 막을 근거는 없다.
     * 다만 가리키는 것은 실제 냄새라 끄지 않고 경고로 남긴다 — 고칠 때 참고한다.
     */
    files: ['**/*.{ts,tsx}'],
    rules: {
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/purity': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/immutability': 'warn',
      'react-hooks/static-components': 'warn',
      'react-hooks/incompatible-library': 'warn',
      /*
       * Fast Refresh 편의에 관한 규칙이지 정확성 문제가 아니다. 지금 걸리는 곳은 전부
       * EMPTY_PROJECT·validateProject 처럼 그 컴포넌트 곁에 두는 게 옳은 상수·함수라,
       * 파일을 쪼개면 코드만 나빠지고 잡히는 결함은 없다. 끄지 않고 경고로 남긴다.
       */
      'react-refresh/only-export-components': 'warn',
    },
  },
  {
    /*
     * shadcn 컴포넌트는 상류에서 받아 그대로 두는 파일이다(vendoring).
     * only-export-components 는 "한 파일에 컴포넌트 하나"를 전제하는데,
     * shadcn 은 Card/CardHeader/CardTitle 을 한 파일에서 내보내는 것이 설계다. 규칙이 안 맞는다.
     */
    files: ['src/components/ui/**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/restrict-template-expressions': 'warn',
      '@typescript-eslint/no-unsafe-assignment': 'warn',
      '@typescript-eslint/no-unsafe-member-access': 'warn',
      '@typescript-eslint/no-unsafe-argument': 'warn',
    },
  },
  {
    // 테스트는 노드 전역과 목(mock) 때문에 규칙 몇 개가 계속 걸린다.
    files: ['**/*.test.{ts,tsx}', 'src/test/**'],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
    },
  },
);
