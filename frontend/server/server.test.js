// @vitest-environment node
//
// The web server: static SPA, same-origin /api proxy, Easy Auth token
// forwarding, health, and security headers. [HOST-2]
import http from 'node:http';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { applyIdentity, createApp, SECURITY_HEADERS } from './app.js';

let upstream;
let upstreamUrl;
let dist;

beforeAll(async () => {
  // A stand-in API that echoes what it received.
  upstream = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ path: req.url, method: req.method, headers: req.headers }));
  });
  await new Promise((resolve) => upstream.listen(0, '127.0.0.1', resolve));
  upstreamUrl = `http://127.0.0.1:${upstream.address().port}`;

  dist = mkdtempSync(path.join(tmpdir(), 'tcc-dist-'));
  writeFileSync(path.join(dist, 'index.html'), '<!doctype html><title>Tax Credit Copilot</title><div id="root"></div>');
  mkdirSync(path.join(dist, 'assets'));
  writeFileSync(path.join(dist, 'assets', 'app-abc123.js'), 'console.log(1)');
});

afterAll(() => {
  upstream.close();
  rmSync(dist, { recursive: true, force: true });
});

const app = () => createApp({ apiBaseUrl: upstreamUrl, distDir: dist });

describe('health', () => {
  it('answers /healthz without touching the API', async () => {
    const res = await request(app()).get('/healthz');
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: 'ok', api_configured: true });
  });
});

describe('the /api proxy', () => {
  it('forwards /api/* to the API with the path intact', async () => {
    const res = await request(app()).get('/api/health?x=1');
    expect(res.status).toBe(200);
    expect(res.body.path).toBe('/api/health?x=1');
  });

  it('forwards the Easy Auth token as a bearer token', async () => {
    const res = await request(app()).get('/api/me').set('X-MS-TOKEN-AAD-ACCESS-TOKEN', 'platform-token');
    expect(res.body.headers.authorization).toBe('Bearer platform-token');
    expect(res.body.headers['x-ms-token-aad-access-token']).toBeUndefined();
  });

  it('drops an Authorization header the browser sent', async () => {
    const res = await request(app()).get('/api/me').set('Authorization', 'Bearer forged');
    expect(res.body.headers.authorization).toBeUndefined();
  });

  it('prefers the platform token over a browser-sent one', async () => {
    const res = await request(app())
      .get('/api/me')
      .set('Authorization', 'Bearer forged')
      .set('X-MS-TOKEN-AAD-ACCESS-TOKEN', 'platform-token');
    expect(res.body.headers.authorization).toBe('Bearer platform-token');
  });

  it('proxies POST bodies', async () => {
    const res = await request(app()).post('/api/claims/assess').send({ client_id: 1 });
    expect(res.body.method).toBe('POST');
    expect(res.body.path).toBe('/api/claims/assess');
  });

  it('answers 503 rather than guessing when no API is configured', async () => {
    const res = await request(createApp({ apiBaseUrl: '', distDir: dist })).get('/api/health');
    expect(res.status).toBe(503);
  });

  it('answers 502 when the API is down', async () => {
    const res = await request(createApp({ apiBaseUrl: 'http://127.0.0.1:1', distDir: dist })).get('/api/health');
    expect(res.status).toBe(502);
  });
});

describe('the SPA', () => {
  it('serves index.html for client-side routes', async () => {
    const res = await request(app()).get('/c/1001/u/GA_1');
    expect(res.status).toBe(200);
    expect(res.text).toContain('Tax Credit Copilot');
    expect(res.headers['cache-control']).toBe('no-cache');
  });

  it('serves hashed assets with a long immutable cache', async () => {
    const res = await request(app()).get('/assets/app-abc123.js');
    expect(res.status).toBe(200);
    expect(res.headers['cache-control']).toContain('immutable');
  });

  it('404s a missing asset rather than serving the app shell as JavaScript', async () => {
    const res = await request(app()).get('/assets/missing.js');
    expect(res.status).toBe(404);
  });
});

describe('security headers', () => {
  it('sets every header on every response', async () => {
    for (const url of ['/', '/healthz', '/api/health']) {
      const res = await request(app()).get(url);
      for (const name of Object.keys(SECURITY_HEADERS)) {
        expect(res.headers[name.toLowerCase()], `${name} on ${url}`).toBe(SECURITY_HEADERS[name]);
      }
      expect(res.headers['x-powered-by']).toBeUndefined();
    }
  });
});

describe('applyIdentity', () => {
  const fakeProxyReq = () => {
    const headers = { authorization: 'Bearer forged' };
    return {
      headers,
      removeHeader: (n) => { delete headers[n]; },
      setHeader: (n, v) => { headers[n] = v; },
    };
  };

  it('leaves no Authorization when there is no platform token', () => {
    const proxyReq = fakeProxyReq();
    applyIdentity(proxyReq, { headers: {} });
    expect(proxyReq.headers.authorization).toBeUndefined();
  });

  it('ignores a blank platform token', () => {
    const proxyReq = fakeProxyReq();
    applyIdentity(proxyReq, { headers: { 'x-ms-token-aad-access-token': '  ' } });
    expect(proxyReq.headers.authorization).toBeUndefined();
  });
});
