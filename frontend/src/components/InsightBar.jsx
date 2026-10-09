import { useEffect, useRef, useState } from 'react';
import {
  ChevronDown, ChevronRight, Info, Loader2, ShieldCheck, Sparkles, TriangleAlert,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { streamPageSummary } from '../api.js';

/**
 * The line above a page's data: a short caption, the notes behind it, and a
 * Copilot summary the reader opens when they want the story.
 *
 * 29 Sep. The page-opening banners pointed at single data points — "0.8 jobs
 * from qualifying: Ironbridge" — above a grid that already said so. James: "let
 * the data do the talking." So each page now carries ONE quiet line:
 *
 * - `caption` — the counts, small, where a banner used to be.
 * - `notes` — what used to be banner caveats (placeholder floor, prototype
 *   designations, the run behind the figures). Behind an ⓘ, on hover or click.
 *   They stay IN THE DOM so a disclosure is never one render away from gone.
 * - `request` — the page's scope for `/api/summary`. The summary is COLLAPSED
 *   and runs only when opened: a narration costs ~10 seconds and a Foundry
 *   call, and most visits are for the grid.
 *
 * The summary's figures come from a brief built from this page's own payload
 * [ADR-004]; the prose is the model's. So the panel says which it is, and
 * reports the backend's check of every figure it stated against that brief.
 */
export default function InsightBar({ caption = null, notes = [], request = null }) {
  const shown = notes.filter(Boolean);
  const [open, setOpen] = useState(false);
  // Once opened it stays mounted, hidden when collapsed, so closing and
  // re-opening does not pay for a second narration of the same page.
  const [opened, setOpened] = useState(false);
  const key = request ? JSON.stringify(request) : '';
  // A new scope while collapsed drops the old summary rather than narrating
  // the new one unseen; while open, the re-keyed panel narrates it.
  const openRef = useRef(open);
  openRef.current = open;
  useEffect(() => {
    if (!openRef.current) setOpened(false);
  }, [key]);
  return (
    <section className="tcc-insight" aria-label="Summary">
      <div className="tcc-insight-row">
        {caption ? <div className="tcc-insight-caption">{caption}</div> : null}
        {shown.length ? <Notes notes={shown} /> : null}
        {request ? (
          <button
            type="button"
            className={`tcc-copilot-toggle${open ? ' open' : ''}`}
            aria-expanded={open}
            onClick={() => { setOpen((v) => !v); setOpened(true); }}
          >
            <Sparkles size={13} aria-hidden="true" />
            Copilot summary
            {open ? <ChevronDown size={13} aria-hidden="true" /> : <ChevronRight size={13} aria-hidden="true" />}
          </button>
        ) : null}
      </div>
      {opened && request ? (
        <div hidden={!open}><CopilotSummary key={key} request={request} /></div>
      ) : null}
    </section>
  );
}

/** ⓘ — hover to read, click to pin. The text is always rendered, only hidden. */
function Notes({ notes }) {
  const [pinned, setPinned] = useState(false);
  return (
    <span className={`tcc-notes${pinned ? ' pinned' : ''}`}>
      <button
        type="button"
        className="tcc-notes-btn"
        aria-expanded={pinned}
        aria-label="Notes about these figures"
        title="Notes about these figures"
        onClick={() => setPinned((v) => !v)}
      >
        <Info size={14} aria-hidden="true" />
      </button>
      <span className="tcc-notes-body" role="note">
        {notes.map((note, index) => (
          // eslint-disable-next-line react/no-array-index-key
          <span key={index} className="tcc-note">{note}</span>
        ))}
      </span>
    </span>
  );
}

/**
 * Streams once per scope while open. Four outcomes, each said plainly:
 * narrated and checked, narrated with a figure the data does not hold,
 * Copilot unavailable (the computed facts instead), or an error.
 */
function CopilotSummary({ request }) {
  const [text, setText] = useState('');
  const [facts, setFacts] = useState(null);
  const [check, setCheck] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setText(''); setFacts(null); setCheck(null); setError(null); setRunning(true);
    streamPageSummary(request, ({ event, data }) => {
      if (event === 'token') setText((t) => t + (data.content || ''));
      else if (event === 'fallback') setFacts(data);
      else if (event === 'check') setCheck(data);
      else if (event === 'error') setError(data.detail || 'The summary could not be written.');
    }, controller.signal)
      .catch((e) => { if (e.name !== 'AbortError') setError(String(e.message || e)); })
      .finally(() => { if (!controller.signal.aborted) setRunning(false); });
    return () => controller.abort();
    // `request` is fixed per mount: the parent re-keys the panel on a new scope.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const unsupported = check?.unsupported || [];
  return (
    <div className="tcc-copilot-panel" aria-live="polite">
      {error ? <p className="tcc-copilot-error">{error}</p> : null}
      {facts ? (
        <>
          <ul className="tcc-copilot-facts">
            {(facts.facts || []).map((fact) => <li key={fact}>{fact}</li>)}
          </ul>
          <p className="tcc-copilot-foot"><Info size={12} aria-hidden="true" /> {facts.note}</p>
        </>
      ) : null}
      {!facts && text ? (
        <div className="tcc-copilot-text">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      ) : null}
      {running && !text && !facts && !error ? (
        <p className="tcc-copilot-wait"><Loader2 size={13} className="spin" aria-hidden="true" /> Reading this page&apos;s figures…</p>
      ) : null}
      {!facts && !error && (text || !running) ? (
        <p className="tcc-copilot-foot">
          {running ? null : unsupported.length ? (
            <span className="warn">
              <TriangleAlert size={12} aria-hidden="true" /> {unsupported.join(', ')}{' '}
              {unsupported.length === 1 ? 'does' : 'do'} not appear in this page&apos;s data — check before quoting.
            </span>
          ) : check ? (
            <span className="ok"><ShieldCheck size={12} aria-hidden="true" /> Every figure checked against this page&apos;s data.</span>
          ) : null}
          <span>AI-written from this page&apos;s figures. The figures are computed; the wording is not.</span>
        </p>
      ) : null}
    </div>
  );
}


/** One line naming the run behind every figure on a page. A note, not a banner. */
export function provenanceLine(run) {
  if (!run) return null;
  const parts = [`Run ${String(run.run_id || '').slice(0, 12)}`];
  if (run.produced_at) parts.push(`produced ${run.produced_at}`);
  if (run.rule_pack_version) parts.push(`statute ${run.rule_pack_version}`);
  if (run.code_commit) parts.push(`code ${String(run.code_commit).slice(0, 7)}`);
  return parts.join(' · ');
}