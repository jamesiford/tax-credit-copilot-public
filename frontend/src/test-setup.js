/**
 * Vitest setup. Runs before every test file.
 *
 * `jest-dom` adds DOM-shaped matchers (`toBeInTheDocument`, `toHaveTextContent`)
 * so a render assertion reads like the thing it is checking.
 */
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// jsdom does not implement these, and components that use them would otherwise
// throw during a render test for reasons that have nothing to do with the test.
//
// Assigned UNCONDITIONALLY. jsdom defines `window.scrollTo` — it just throws
// "Not implemented" when called — so an `||` guard keeps the throwing version
// and the error surfaces as an unhandled rejection that can report a whole
// green file as incomplete.
//
// Skipped under the Node environment (server/ tests), which has no window.
if (typeof window !== 'undefined') {
  window.scrollTo = () => {};

  if (!window.matchMedia) {
    window.matchMedia = (query) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    });
  }
}
