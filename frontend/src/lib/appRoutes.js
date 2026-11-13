/**
 * The paths the shell (`App.jsx`, `parseRouteState`) understands, in one place so the router table and its test agree.
 *
 * `/:view` matches ONE segment, so a nested page needs its own entry: without `/runs/:batchId` and `/programs/*` a
 * pasted, bookmarked or refreshed batch, program or draft link fell through to the catch-all and landed on the book. [F07.2]
 */
export const APP_ROUTE_PATHS = [
  '/',
  '/:view',
  '/runs/:batchId',
  '/programs/*',
  '/c/:clientId',
  '/c/:clientId/:view',
  '/c/:clientId/u/:unitId',
  '/c/:clientId/e/:token',
];
