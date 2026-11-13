/*
 * Why: the one place the portal says that statute values are unverified until a person checks them against the primary source,
 * so the warning cannot be softened on one page and sharpened on another.
 * Never: say or imply a value is verified, or hide behind a dismiss button.
 */
import Callout from '../ui/Callout.jsx';
import { STATUTE_WARNING } from '../../lib/programs.js';

export default function UnverifiedNotice({ title = 'Not verified' }) {
  return <Callout tone="partial" title={title}><p>{STATUTE_WARNING}</p></Callout>;
}
