import { Building2 } from 'lucide-react';
import PageHeader from './PageHeader.jsx';
import Stepper from './ui/Stepper.jsx';
import { clientSteps, unavailableReason } from '../lib/clientFlow.js';
import { methodLabel, rulePackLabel, runLabel } from '../lib/reviewMeta.js';

/**
 * The client's review header: a way back, who and what is on screen, and the
 * flow across the client's views.
 *
 * Every value is one the page already holds (the scope, the run the grid read,
 * the reading it is showing): nothing here is fetched or computed. A value that
 * is not known yet is omitted by `MetaLine`, never shown as a bare label.
 *
 * `current` is a step id derived from the ROUTE by the caller, so the stepper
 * cannot disagree with the page. It never gates content.
 */
export default function ClientHeader({
  clientId, clientName, industry = null, year = null, search = '', current = null,
  clientScope = null, run = null, method = null, onBack, actions = null,
}) {
  const steps = clientSteps({ clientId, year, search, current, clientScope });
  const reason = unavailableReason(clientScope);

  const meta = [
    { label: 'Client', value: industry ? `Account ${clientId} · ${industry}` : `Account ${clientId}` },
    { label: 'Tax year', value: year != null ? `TY${year}` : null },
    { label: 'Method', value: methodLabel(method) },
    { label: 'Run', value: runLabel(run) },
    { label: 'Rule pack', value: rulePackLabel(run?.rule_pack_version) },
  ];

  return (
    <>
      <PageHeader
        compact
        back={onBack ? { label: 'Portfolio', onClick: onBack } : null}
        icon={<Building2 size={22} aria-hidden="true" />}
        title={clientName || 'This client'}
        meta={meta}
      />
      <div className="tcc-review-flow">
        <Stepper steps={steps} label="Client review" />
        {actions}
      </div>
      {reason ? <p className="tcc-review-note" role="note">{reason}</p> : null}
    </>
  );
}
