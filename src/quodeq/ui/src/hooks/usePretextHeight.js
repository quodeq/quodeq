/**
 * usePretextHeight — measure the rendered height of a multiline text block
 * at the ref'd element's current width, without actually rendering anywhere.
 *
 * Uses `@chenglou/pretext` to do layout math in a canvas-backed, DOM-free way
 * and a `ResizeObserver` to re-measure when the container width changes. The
 * returned `height` is the pixel height the text will occupy inside the ref.
 *
 * Typical use: pre-compute the collapsed/expanded height of a REASON/DETAIL
 * paragraph so CSS transitions don't jump, and so a future virtualiser knows
 * the row height before it renders.
 *
 *   const ref = useRef(null);
 *   const { height, lineCount } = usePretextHeight(ref, text, { lineHeight: 18 });
 *   return <p ref={ref} style={{ minHeight: height }}>{text}</p>;
 *
 * @param {React.RefObject<HTMLElement>} ref - Element whose width drives layout.
 * @param {string | null | undefined} text - Text to measure. Null/empty returns 0.
 * @param {object} [options]
 * @param {number} [options.lineHeight] - Px per line. Defaults to the element's
 *   computed line-height, falling back to 1.5×font-size.
 * @param {string} [options.font] - Explicit CSS font shorthand. Defaults to the
 *   element's computed font.
 * @returns {{ height: number, lineCount: number }}
 */
import { useState, useLayoutEffect } from 'react';
import { measureText, cssFontFromElement } from '../utils/pretext.js';

const DEFAULT_LINE_HEIGHT = 18;

export default function usePretextHeight(ref, text, options = {}) {
  const [size, setSize] = useState({ height: 0, lineCount: 0 });

  useLayoutEffect(() => {
    const el = ref && ref.current;
    if (!el || !text) {
      setSize({ height: 0, lineCount: 0 });
      return undefined;
    }

    const measure = () => {
      const font = options.font || cssFontFromElement(el);
      let lineHeight = options.lineHeight;
      if (!lineHeight && typeof window !== 'undefined') {
        const cs = window.getComputedStyle(el);
        const parsed = parseFloat(cs.lineHeight);
        if (!Number.isNaN(parsed) && parsed > 0) {
          lineHeight = parsed;
        } else {
          const fontSize = parseFloat(cs.fontSize);
          if (!Number.isNaN(fontSize) && fontSize > 0) lineHeight = fontSize * 1.5;
        }
      }
      if (!lineHeight) lineHeight = DEFAULT_LINE_HEIGHT;
      const width = el.clientWidth || 0;
      const next = measureText(text, font, width, lineHeight);
      setSize((prev) =>
        prev.height === next.height && prev.lineCount === next.lineCount ? prev : next
      );
    };

    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref, text, options.lineHeight, options.font]);

  return size;
}
