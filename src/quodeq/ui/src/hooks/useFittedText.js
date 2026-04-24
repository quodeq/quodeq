/**
 * useFittedText — middle-truncate `text` so it fits inside the ref'd element's
 * current width. Re-fits on resize via ResizeObserver. Uses pretext's canvas-
 * backed measurement under the hood — no DOM probing of fake elements.
 *
 *   const ref = useRef(null);
 *   const fitted = useFittedText(ref, 'auth/deep/path/jwt.py:42');
 *   return <span ref={ref} title="auth/deep/path/jwt.py:42">{fitted}</span>;
 *
 * @param {React.RefObject<HTMLElement>} ref
 * @param {string | null | undefined} text
 * @param {object} [options]
 * @param {string} [options.font] - CSS font shorthand; defaults to the ref's
 *   computed font.
 * @param {string} [options.ellipsis='\u2026']
 * @returns {string}
 */
import { useLayoutEffect, useState } from 'react';
import { fitMiddleTruncate, fitEndTruncate, cssFontFromElement } from '../utils/pretext.js';

/**
 * @param {React.RefObject<HTMLElement>} ref
 * @param {string | null | undefined} text
 * @param {object} [options]
 * @param {'middle'|'end'} [options.mode='middle'] - 'middle' preserves both
 *   ends (good for paths like `auth/.../jwt.py:42`); 'end' preserves the
 *   head (good for comma-lists where the leading items are most useful).
 * @param {string} [options.font]
 * @param {string} [options.ellipsis='\u2026']
 */
export default function useFittedText(ref, text, options = {}) {
  const [fitted, setFitted] = useState(text || '');

  useLayoutEffect(() => {
    const el = ref && ref.current;
    if (!el) {
      setFitted(text || '');
      return undefined;
    }
    if (!text) {
      setFitted('');
      return undefined;
    }

    const fitter = options.mode === 'end' ? fitEndTruncate : fitMiddleTruncate;

    const compute = () => {
      const font = options.font || cssFontFromElement(el);
      const width = el.clientWidth || 0;
      const ellipsis = options.ellipsis || '\u2026';
      const next = fitter(text, font, width, ellipsis);
      setFitted((prev) => (prev === next ? prev : next));
    };

    compute();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(compute);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref, text, options.font, options.ellipsis, options.mode]);

  return fitted;
}
