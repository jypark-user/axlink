import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    // 컨테이너에서는 API 가 다른 컨테이너라 주소를 받는다(infra/docker-compose.yml).
    proxy: {
      '/api': { target: process.env.AXLINK_API_PROXY ?? 'http://localhost:8080', changeOrigin: true },
    },
    // Windows 폴더를 컨테이너에 붙이면 파일 변경 알림이 오지 않아 polling 으로 본다.
    watch: process.env.AXLINK_VITE_POLLING ? { usePolling: true, interval: 300 } : undefined,
  },
});
