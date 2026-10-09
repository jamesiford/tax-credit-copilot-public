import { useMemo } from 'react';
import EmployeeDrill from '../components/EmployeeDrill.jsx';
import Breadcrumb from '../components/Breadcrumb.jsx';

/**
 * One employee's calculation walk, as a page.
 *
 * It was a modal, which is why `selection_decision` had nowhere to breathe:
 * "outside fiscal window", "shorter than seven days" and "filtered by pay code"
 * are three different explanations and a reviewer has to tell them apart.
 *
 * The route carries the RECORD TOKEN, never the employee id. The id may be
 * displayed once authorised; it may not appear in a URL, a log or telemetry.
 */
export default function EmployeePage({
  clientId, token, year, method = 'min_max', clientName, unitId,
  onOpenPortfolio, onOpenClient, onOpenUnit, onOpenWhatIf, onBack,
}) {
  // A token resolves only where the run that minted it is served. Passing the
  // client-year is what makes this the per-client drill rather than the sealed
  // one — and it must be an OBJECT: the previous call site passed a bare year,
  // which spread to nothing and silently fell back to no context at all.
  //
  // Memoised because the drill fetches whenever `context` changes identity. A
  // fresh object per render re-posted the drill on every shell re-render.
  const context = useMemo(
    () => (clientId ? { taxYear: year, accountId: clientId } : null),
    [clientId, year],
  );

  const trail = [
    { key: 'p', label: 'Portfolio', onClick: onOpenPortfolio },
    clientId ? { key: 'c', label: clientName || `Account ${clientId}`, onClick: onOpenClient } : null,
    unitId ? { key: 'u', label: unitId, onClick: onOpenUnit } : null,
    { key: 'e', label: 'Employee walk' },
  ];

  return (
    <div>
      <Breadcrumb trail={trail} />
      <EmployeeDrill
        recordToken={token}
        context={context}
        method={method}
        onOpenWhatIf={onOpenWhatIf}
        onClose={onBack}
      />
    </div>
  );
}
