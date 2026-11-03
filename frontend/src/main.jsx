/**
 * Application entry. One shell.
 *
 * There used to be two: a synthetic demo portal at `/` and the parity workspace
 * at `/golden`. They told different stories over different data, and the front
 * door opened on the wrong one — a viewer's first impression was a fictional
 * logistics company, which undercuts every claim the real workspace makes.
 *
 * `/golden` is kept as a redirect rather than removed, because it is the URL
 * that has been shared. The path keeps its old spelling for the same reason the
 * assumption-set IDs do: it is an identifier that escaped, not a name we choose.
 */
import React, { lazy, Suspense } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
// Typefaces are BUNDLED, not hotlinked: a demo on a hotel network that cannot
// reach fonts.gstatic.com would silently fall back to Segoe UI, which is the
// exact failure this replaces. Latin only, and only the weights the stylesheet
// asks for. The active face is a theme token (`--font-sans`): Poppins in the
// modern theme, Roboto in the classic one and in a customer overlay that
// points it back.
import './styles/fonts.css';
import App from './App.jsx';
import { applyTheme } from './brand.config.js';
import './styles/tokens/index.css';
import './index.css';
import './styles/chrome-modern.css';
import './styles/page-patterns.css';
import './styles/overlay.css';

// Applied before the first render, so the page never paints in one theme and flips.
applyTheme();

// The owner's visual review surface. `import.meta.env.DEV` is a build-time
// constant, so the dynamic import (and the page) is dropped from production.
const Styleguide = import.meta.env.DEV ? lazy(() => import('./pages/Styleguide.jsx')) : null;

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        {Styleguide ? (
          <Route path="/__styleguide" element={<Suspense fallback={null}><Styleguide /></Suspense>} />
        ) : null}
        <Route path="/" element={<App />} />
        <Route path="/:view" element={<App />} />
        <Route path="/c/:clientId" element={<App />} />
        <Route path="/c/:clientId/:view" element={<App />} />
        <Route path="/c/:clientId/u/:unitId" element={<App />} />
        <Route path="/c/:clientId/e/:token" element={<App />} />
        <Route path="/golden/*" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
