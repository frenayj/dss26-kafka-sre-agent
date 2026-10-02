import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    // The web BFF in dev; the deployed app is served from the same origin as the BFF.
    proxy: {'/web': {target: process.env.BFF_DEV_URL ?? 'http://localhost:8080', changeOrigin: true}},
  },
  test: {
    environment: 'jsdom',
  },
});
