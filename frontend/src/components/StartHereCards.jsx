import { Building2, PhoneCall, ShieldCheck, UserPlus } from 'lucide-react';
import TaskCard from './ui/TaskCard.jsx';
import './StartHere.css';

/**
 * The four things somebody opens this product to do, as cards.
 *
 * Each is a real link (`href`), so a modifier-click opens a new tab, and each
 * routes in-app on a plain click. They are shortcuts to places that already
 * exist, not features: nothing here computes or invents a figure.
 *
 *   Who to call        the ranked book, below
 *   Review a client    the best-ranked client's page
 *   What if we hire…   that client's What-if tab
 *   Prove the work     the audit trail
 *
 * "Review a client" and "What if" need a client, and the book's first row is the
 * one the ranking says matters most. With an empty book they fall back to the
 * book itself rather than linking to a client that does not exist.
 *
 * Never: link to a client that is not in the book, or phrase a card as a result.
 */
export default function StartHereCards({ firstClientId, onNavigate, onShowBook, id }) {
  const client = firstClientId != null ? `/c/${encodeURIComponent(firstClientId)}` : null;

  const go = (href) => (event) => {
    event.preventDefault();
    onNavigate(href);
  };
  const toBook = (event) => {
    event.preventDefault();
    onShowBook();
  };

  return (
    <section id={id} className="start-here" aria-label="Start here">
      <TaskCard
        href="#targeting"
        icon={<PhoneCall size={20} />}
        title="Who to call"
        description="Clients ranked by the reason to act"
        onClick={toBook}
      />
      <TaskCard
        href={client || '#targeting'}
        icon={<Building2 size={20} />}
        title="Review a client"
        description={client ? 'Open the best-ranked client' : 'Pick one from the book'}
        onClick={client ? go(client) : toBook}
      />
      <TaskCard
        href={client ? `${client}?ctab=whatif` : '#targeting'}
        icon={<UserPlus size={20} />}
        title="What if we hire…"
        description="See what extra jobs would change"
        onClick={client ? go(`${client}?ctab=whatif`) : toBook}
      />
      <TaskCard
        href="/evidence"
        icon={<ShieldCheck size={20} />}
        title="Prove the work"
        description="The audit trail behind each figure"
        onClick={go('/evidence')}
      />
    </section>
  );
}
