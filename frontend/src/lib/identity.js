/**
 * Who the shell is talking to, derived from the identity the API reports.
 *
 * `/api/me` carries a UPN, not a display name, so the greeting uses the first
 * word of the local part ("jane.doe@example.com" -> "Jane"). That is a guess at
 * a name, which is why it is only ever used to say hello and never shown as the
 * account's identity: the account menu shows the UPN itself.
 *
 * `null` means "do not greet by name": nobody is signed in (AUTH_MODE=none), or
 * the local part is not something that reads as a name.
 */
export function firstName(identity) {
  if (!identity?.authenticated || !identity.upn) return null;
  const local = String(identity.upn).split('@')[0];
  const word = local.split(/[._\-+\d]/).find(Boolean);
  if (!word || word.length < 2) return null;
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
}

/** One or two letters for the avatar. */
export function initials(identity) {
  if (!identity?.upn) return '';
  const local = String(identity.upn).split('@')[0];
  const parts = local.split(/[._\-+]/).filter(Boolean);
  const letters = parts.length > 1
    ? parts[0][0] + parts[1][0]
    : (parts[0] || '').slice(0, 2);
  return letters.toUpperCase();
}

/** The hero's heading: by name when we have one, otherwise the plain welcome. */
export function greeting(identity) {
  const name = firstName(identity);
  return name ? `Hi, ${name}` : 'Welcome back';
}
