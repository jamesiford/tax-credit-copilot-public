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
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
// Roboto is the house typeface. BUNDLED, not hotlinked: a demo on a
// hotel network that cannot reach fonts.gstatic.com would silently fall back to
// Segoe UI, which is the exact failure this replaces. Latin only, and only the
// five weights the stylesheet actually asks for.
import '@fontsource/roboto/latin-400.css';
import '@fontsource/roboto/latin-500.css';
import '@fontsource/roboto/latin-600.css';
import '@fontsource/roboto/latin-700.css';
import '@fontsource/roboto/latin-800.css';
import App from './App.jsx';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
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
