import { useEffect, useRef } from 'react';

const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled])', 'select:not([disabled])',
  'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(',');

function focusables(root) {
  return [...root.querySelectorAll(FOCUSABLE)].filter(
    (el) => !el.hasAttribute('hidden') && el.getAttribute('aria-hidden') !== 'true',
  );
}

/**
 * Modal behaviour for the Ask workspace, and nothing else:
 *
 *  - focus moves in when it opens (the composer if there is one, else the first
 *    control) and Tab / Shift+Tab wrap inside it;
 *  - Escape closes it;
 *  - while open the page behind is scroll-locked (a class on <html>: the page
 *    keeps its scope and its scroll position, it just cannot move);
 *  - on close, focus returns to what opened it. When that control has since left
 *    the document (the floating launcher is unmounted while the workspace is
 *    open), it falls back to `fallbackId`.
 */
export default function useModal(ref, { open, onClose, fallbackId = 'ask-launcher' }) {
  const opener = useRef(null);
  // Held in a ref so a parent re-rendering with a fresh callback does not re-run
  // the effect, which would forget what opened the workspace.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  // The focus return is deferred a frame, so it must know the workspace did not
  // reopen or unmount in between: a late focus() would steal it from whatever
  // the reader is doing by then.
  const live = useRef({ open, mounted: true });
  live.current.open = open;
  useEffect(() => () => { live.current.mounted = false; }, []);

  useEffect(() => {
    if (!open) return undefined;
    opener.current = document.activeElement;
    document.documentElement.classList.add('ask-open');

    const root = ref.current;
    const first = root?.querySelector('[data-autofocus]') || (root ? focusables(root)[0] : null);
    first?.focus();

    const onKey = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        closeRef.current?.();
        return;
      }
      if (event.key !== 'Tab' || !ref.current) return;
      const items = focusables(ref.current);
      if (!items.length) return;
      const head = items[0];
      const tail = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === head || !ref.current.contains(document.activeElement))) {
        event.preventDefault();
        tail.focus();
      } else if (!event.shiftKey && (document.activeElement === tail || !ref.current.contains(document.activeElement))) {
        event.preventDefault();
        head.focus();
      }
    };
    document.addEventListener('keydown', onKey, true);

    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.documentElement.classList.remove('ask-open');
      const back = opener.current;
      opener.current = null;
      // After the launcher has remounted. When what opened the workspace has left
      // the page (the floating launcher unmounts while it is open, which leaves
      // `document.body` as the active element) go back to the launcher instead.
      requestAnimationFrame(() => {
        if (!live.current.mounted || live.current.open) return;
        const usable = back && back.isConnected && back !== document.body;
        const target = usable ? back : document.getElementById(fallbackId);
        target?.focus?.();
      });
    };
  }, [open, ref, fallbackId]);
}
