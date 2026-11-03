import Callout from '../ui/Callout.jsx';
import KpiTile, { KpiRow } from '../ui/KpiTile.jsx';

/**
 * Draws validated evidence blocks (lib/evidence.js) and nothing else.
 *
 * Every string is rendered as it arrived. There is no number formatting, no
 * rounding, no summing, no re-ordering here, and none may be added: the pane
 * exists so the figure on screen is the figure the platform wrote.
 */

function Table({ block }) {
  return (
    <div className="ask-table-wrap">
      <table className="tbl-compact ask-table">
        {block.title ? <caption>{block.title}</caption> : null}
        <thead>
          <tr>
            {block.columns.map((column, i) => (
              <th key={`${column}-${i}`} scope="col" className={block.align?.[i] === 'right' ? 'num' : undefined}>
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) => (
                <td key={c} className={block.align?.[c] === 'right' ? 'num' : undefined}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Block({ block }) {
  switch (block.kind) {
    case 'text':
      return (
        <div className="ask-block">
          {block.title ? <h3 className="ask-block-title">{block.title}</h3> : null}
          <p className="ask-text">{block.text}</p>
        </div>
      );
    case 'list':
      return (
        <div className="ask-block">
          {block.title ? <h3 className="ask-block-title">{block.title}</h3> : null}
          <ul className="ask-list">
            {block.rows.map((row, i) => <li key={i}>{row}</li>)}
          </ul>
        </div>
      );
    case 'kpis':
      return (
        <KpiRow label={block.title || 'Figures'}>
          {block.rows.map((row, i) => (
            <KpiTile key={`${row.label}-${i}`} label={row.label} value={row.value} sub={row.sub} tone={row.tone} />
          ))}
        </KpiRow>
      );
    case 'table':
      return <Table block={block} />;
    case 'callout':
      return <Callout title={block.title || 'Why'} tone={block.tone}>{block.text}</Callout>;
    default:
      return null;
  }
}

export default function EvidenceBlocks({ blocks }) {
  return (
    <div className="ask-blocks">
      {blocks.map((block, i) => <Block key={i} block={block} />)}
    </div>
  );
}
