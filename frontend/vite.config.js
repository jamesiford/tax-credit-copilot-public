import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * Preload the primary faces from the BUNDLE.
 *
 * A font declared in a stylesheet is only discovered after the CSS has arrived
 * and the first paint needs it, so the text paints in the fallback and swaps. A
 * `<link rel="preload">` in the document starts the request with the HTML. The
 * file names carry a content hash, so they cannot be written by hand in
 * index.html: this reads them from the emitted bundle instead, and so cannot go
 * stale. Only the faces first paint needs: Poppins 400 (body and chrome) and
 * Roboto 400 (the data grids).
 */
function preloadFonts(faces) {
  let base = '/';
  return {
    name: 'preload-primary-fonts',
    apply: 'build',
    configResolved(config) { base = config.base; },
    transformIndexHtml(_html, ctx) {
      return Object.keys(ctx.bundle || {})
        .filter((file) => faces.some((face) => file.includes(face)))
        .map((file) => ({
          tag: 'link',
          attrs: {
            rel: 'preload', as: 'font', type: 'font/woff2', crossorigin: '', href: `${base}${file}`,
          },
          injectTo: 'head-prepend',
        }));
    },
  };
}

export default defineConfig({
  plugins: [react(), preloadFonts(['poppins-latin-400-normal', 'roboto-latin-400-normal'])],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.js'],
    // server/ runs under Node (per-file `@vitest-environment node`).
    include: ['src/**/*.test.{js,jsx}', 'server/**/*.test.js'],
  },
});
