import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const PROXY_PORT = process.env.PORT ?? '8900';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    // En modo dev el frontend corre en Vite y el proxy en su propio puerto; así
    // el token sigue viviendo solo en el backend, igual que en producción.
    proxy: { '/api': `http://127.0.0.1:${PROXY_PORT}` },
  },
  build: { outDir: 'dist', sourcemap: true },
});
