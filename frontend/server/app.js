// Tax Credit Copilot web server (Node 24 LTS, App Service Linux). [HOST-2]
//
// Serves the built SPA from `dist/` and proxies `/api/*` to the API, so the
// browser keeps a same-origin `/api` exactly as it had behind nginx.
//
// Identity: App Service Authentication (Easy Auth) signs the user in and
// injects their access token as `X-MS-TOKEN-AAD-ACCESS-TOKEN`. This server
// forwards it to the API as `Authorization: Bearer`, and DROPS any
// `Authorization` header the browser sent: the only token the API ever sees is
// one the platform issued for this session.

import express from 'express';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createProxyMiddleware } from 'http-proxy-middleware';

export const EASY_AUTH_TOKEN_HEADER = 'x-ms-token-aad-access-token';

// The SPA uses inline style attributes (charting and map libraries), so styles
// allow 'unsafe-inline'; scripts do not. Fonts are self-hosted.
export const SECURITY_HEADERS = {
  'Content-Security-Policy': [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
  ].join('; '),
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
  'Cross-Origin-Opener-Policy': 'same-origin',
};

function securityHeaders(_req, res, next) {
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) res.setHeader(name, value);
  next();
}

/**
 * Rewrite the outbound API request's credentials.
 * Exported so the rule is testable without a socket.
 */
export function applyIdentity(proxyReq, req) {
  proxyReq.removeHeader('authorization');
  const token = req.headers[EASY_AUTH_TOKEN_HEADER];
  proxyReq.removeHeader(EASY_AUTH_TOKEN_HEADER);
  if (typeof token === 'string' && token.trim()) {
    proxyReq.setHeader('authorization', `Bearer ${token.trim()}`);
  }
}

export function createApp({ apiBaseUrl = process.env.API_BASE_URL, distDir } = {}) {
  const app = express();
  app.disable('x-powered-by');
  app.use(securityHeaders);

  app.get('/healthz', (_req, res) => {
    res.set('Cache-Control', 'no-store').json({ status: 'ok', api_configured: Boolean(apiBaseUrl) });
  });

  if (apiBaseUrl) {
    app.use(createProxyMiddleware({
      target: apiBaseUrl,
      changeOrigin: true,
      pathFilter: '/api',
      // Streaming answers (chat, page summaries) are long-lived.
      proxyTimeout: 300_000,
      timeout: 300_000,
      on: {
        proxyReq: (proxyReq, req) => applyIdentity(proxyReq, req),
        error: (_err, _req, res) => {
          if (res && !res.headersSent && typeof res.status === 'function') {
            res.status(502).json({ detail: 'API unreachable' });
          } else if (res && typeof res.end === 'function') {
            res.end();
          }
        },
      },
    }));
  } else {
    app.use('/api', (_req, res) => {
      res.status(503).json({ detail: 'API_BASE_URL is not configured on the web app' });
    });
  }

  const dist = distDir ?? path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist');
  const indexHtml = path.join(dist, 'index.html');

  // Hashed bundles never change; index.html must, so a deploy lands on the next load.
  app.use('/assets', express.static(path.join(dist, 'assets'), { immutable: true, maxAge: '365d', fallthrough: false }));
  app.use(express.static(dist, { index: false, maxAge: 0 }));

  // SPA fallback: any GET that is not a file serves the app shell.
  app.use((req, res, next) => {
    if (req.method !== 'GET' && req.method !== 'HEAD') return next();
    if (!existsSync(indexHtml)) {
      return res.status(503).type('text/plain').send('The web bundle is not built (frontend/dist is missing).');
    }
    res.set('Cache-Control', 'no-cache');
    return res.sendFile(indexHtml);
  });

  return app;
}
