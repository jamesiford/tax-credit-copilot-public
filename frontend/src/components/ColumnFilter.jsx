import { useEffect, useRef, useState } from 'react';
import { Filter, X } from 'lucide-react';
import {
  ENUM, NUMERIC, TEXT, YEAR, describeFilter, hidingLabel, parseNumeric,
} from '../lib/gridFilter.js';

const COMPARATORS = [
  ['>=', 'at least'],
  ['<=', 'at most'],
  ['>', 'more than'],
  ['<', 'less than'],
  ['..', 'between'],
];

function NumericBody({ value, onApply }) {
  const parsed = parseNumeric(value) || { op: '>=', value: '' };
  const [op, setOp] = useState(parsed.op);
  const [a, setA] = useState(parsed.op === '..' ? parsed.min : (parsed.value ?? ''));
  const [b, setB] = useState(parsed.op === '..' ? parsed.max : '');

  const commit = () => {
    if (op === '..') {
      if (a === '' || b === '') return onApply('');
      return onApply(`${a}..${b}`);
    }
    return onApply(a === '' ? '' : `${op}${a}`);
  };

  return (
    <form
      className="colf-body"
      onSubmit={(event) => { event.preventDefault(); commit(); }}
    >
      <select className="colf-op" value={op} onChange={(e) => setOp(e.target.value)} aria-label="Comparator">
        {COMPARATORS.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
      </select>
      <input
        className="colf-num"
        type="number"
        step="any"
        value={a}
        onChange={(e) => setA(e.target.value)}
        aria-label={op === '..' ? 'Lower bound' : 'Value'}
      />
      {op === '..' ? (
        <input
          className="colf-num"
          type="number"
          step="any"
          value={b}
          onChange={(e) => setB(e.target.value)}
          aria-label="Upper bound"
        />
      ) : null}
      <button type="submit" className="btn btn-secondary colf-apply">Apply</button>
    </form>
  );
}

function TextBody({ value, onApply }) {
  const [text, setText] = useState(String(value || '').replace(/^~/, ''));
  return (
    <form
      className="colf-body"
      onSubmit={(event) => { event.preventDefault(); onApply(text.trim() ? `~${text.trim()}` : ''); }}
    >
      <input
        className="colf-text"
        type="search"
        value={text}
        placeholder="contains…"
        onChange={(e) => setText(e.target.value)}
        aria-label="Contains"
      />
      <button type="submit" className="btn btn-secondary colf-apply">Apply</button>
    </form>
  );
}

/**
 * Multi-select over the values PRESENT in the data.
 *
 * A hardcoded option list goes stale the first time a status is renamed, and
 * then offers a filter that matches nothing — which reads as "no rows" rather
 * than "no such value".
 */
function EnumBody({ value, options, format, onApply }) {
  const chosen = new Set(String(value || '').split('|').filter(Boolean));
  const toggle = (option) => {
    const next = new Set(chosen);
    if (next.has(option)) next.delete(option);
    else next.add(option);
    onApply([...next].join('|'));
  };
  if (!options.length) {
    return <p className="colf-body small muted">No values in this column yet.</p>;
  }
  return (
    <div className="colf-body colf-enum">
      {options.map((option) => (
        <label key={option} className="colf-check">
          <input type="checkbox" checked={chosen.has(option)} onChange={() => toggle(option)} />
          <span>{format ? format(option) : option}</span>
        </label>
      ))}
    </div>
  );
}

/**
 * The filter control for ONE column, matched to that column's type.
 *
 * One control for all types was the alternative and it is worse: a free-text
 * box over an enum invites a value that does not exist, and over a number it
 * invites `35` meaning five different things.
 */
export function ColumnFilter({ spec, value, options = [], onChange }) {
  const [open, setOpen] = useState(false);
  const holder = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const away = (event) => { if (!holder.current?.contains(event.target)) setOpen(false); };
    const escape = (event) => { if (event.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  const active = Boolean(String(value || '').trim());
  const apply = (next) => {
    onChange(next);
    if (spec.type !== ENUM && spec.type !== YEAR) setOpen(false);
  };

  return (
    <span className="colf" ref={holder}>
      <button
        type="button"
        className={`colf-toggle${active ? ' active' : ''}`}
        aria-label={`Filter ${spec.label}`}
        aria-expanded={open}
        title={active ? describeFilter(spec, value) : `Filter ${spec.label}`}
        onClick={() => setOpen((was) => !was)}
      >
        <Filter size={11} aria-hidden="true" />
      </button>
      {open ? (
        <div className="colf-pop">
          <div className="colf-head">
            <span>{spec.label}</span>
            {active ? (
              <button type="button" className="tcc-link" onClick={() => { onChange(''); setOpen(false); }}>
                Clear
              </button>
            ) : null}
          </div>
          {spec.type === NUMERIC ? <NumericBody value={value} onApply={apply} /> : null}
          {spec.type === TEXT ? <TextBody value={value} onApply={apply} /> : null}
          {spec.type === ENUM || spec.type === YEAR
            ? <EnumBody value={value} options={options} format={spec.format} onApply={apply} />
            : null}
        </div>
      ) : null}
    </span>
  );
}

/**
 * What the grid is hiding, and the way out of it.
 *
 * Never conditional on there being room for it: a filter the reader forgot they
 * set is how somebody reports a wrong total, so the statement outranks the
 * layout.
 */
export function FilterBar({ specs, filters, shown, total, noun = 'rows', onClear }) {
  const chips = Object.entries(filters || {})
    .map(([key, expr]) => [key, describeFilter(specs[key], expr)])
    .filter(([, text]) => text);
  if (!chips.length) return null;
  return (
    <div className="filter-bar" role="status">
      <span className="filter-bar-count">
        Showing {hidingLabel(shown, total)} {noun}
      </span>
      {chips.map(([key, text]) => (
        <button
          key={key}
          type="button"
          className="filter-chip"
          onClick={() => onClear(key)}
          title="Remove this filter"
        >
          {text}
          <X size={11} aria-hidden="true" />
        </button>
      ))}
      <button type="button" className="tcc-link" onClick={() => onClear(null)}>Clear all</button>
    </div>
  );
}

export { ENUM, NUMERIC, TEXT, YEAR };
