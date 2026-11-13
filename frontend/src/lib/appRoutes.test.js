import { describe, expect, it } from 'vitest';
import { matchRoutes } from 'react-router-dom';
import { APP_ROUTE_PATHS } from './appRoutes.js';

const table = APP_ROUTE_PATHS.map((path) => ({ path }));

describe('the router table', () => {
  it.each([
    '/', '/runs', '/runs/b-partial', '/programs', '/programs/ZZ_DEMO_JTC', '/programs/new', '/programs/draft/d-1',
    '/rules', '/c/2001', '/c/2001/eligibility', '/c/2001/u/GA_GA-010', '/c/2001/e/tok-0001',
  ])('resolves %s to a page, not the catch-all', (url) => {
    expect(matchRoutes(table, url)).not.toBeNull();
  });

  it('does not invent routes for paths the shell does not parse', () => {
    expect(matchRoutes(table, '/runs/b-partial/extra')).toBeNull();
    expect(matchRoutes(table, '/nonsense/at/depth')).toBeNull();
  });
});
