/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Dev/preview forward the API to the gateway; the production bundle is served same-origin behind nginx
// (docker/nginx.conf), whose CSP forbids inline scripts and third-party requests, so the build emits none.
const gateway = process.env.SENTINEL_GATEWAY_URL ?? 'http://localhost:8000';
const proxy = {
  '/api': { target: gateway, changeOrigin: false },
  '/graphql-proxy': { target: gateway, changeOrigin: false },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 3000, strictPort: true, proxy },
  preview: { port: 4173, proxy },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2020',
    modulePreload: { polyfill: false }, // the polyfill is an inline script; modern browsers do not need it
    assetsInlineLimit: 0, // never inline assets as data: URIs (CSP: img-src 'self' data: only for what we choose)
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/setupTests.ts'],
    css: false,
    testTimeout: 20000,
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
