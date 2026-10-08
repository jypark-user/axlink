import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// 앱이 놓일 경로. 외부 공개는 /ax-link/ 다(AXLINK_BASE_PATH). 로컬 개발은 / 그대로다.
// Git Bash 에서 빌드 인자를 넘기면 /ax-link/ 가 C:/Program Files/Git/ax-link/ 로 바뀐 채 들어와
// 화면 파일을 못 찾는 흰 화면이 됐다(10-07). 슬래시로 시작·끝나는 URL 경로만 받는다.
// 같은 규칙을 scripts/check-build.mjs 도 쓴다.
const basePath = process.env.AXLINK_BASE_PATH ?? '/';
if (!/^\/([A-Za-z0-9._-]+\/)*$/.test(basePath)) {
  throw new Error(
    `AXLINK_BASE_PATH 가 URL 경로가 아닙니다: "${basePath}". "/" 나 "/ax-link/" 꼴이어야 합니다. ` +
      'Git Bash 라면 MSYS_NO_PATHCONV=1 을 켜고 다시 빌드하십시오.',
  );
}

export default defineConfig({
  base: basePath,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    // 컨테이너에서는 API 가 다른 컨테이너라 주소를 받는다(infra/docker-compose.yml).
    proxy: {
      '/api': {
        target: process.env.AXLINK_API_PROXY ?? 'http://localhost:8080',
        changeOrigin: true,
      },
    },
    // Windows 폴더를 컨테이너에 붙이면 파일 변경 알림이 오지 않아 polling 으로 본다.
    watch: process.env.AXLINK_VITE_POLLING ? { usePolling: true, interval: 300 } : undefined,
  },
});
