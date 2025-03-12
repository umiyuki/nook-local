import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ['lucide-react'],
  },
  server: {
    host: true,  // 全てのIPアドレスからのアクセスを許可
    port: 5173,  // ポートを明示的に指定
  }
});
