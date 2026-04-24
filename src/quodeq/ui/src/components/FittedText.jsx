/**
 * FittedText — renders `text` inside a span that truncates to fit its
 * container width. Uses the `useFittedText` hook (pretext-backed) so the
 * measurement happens off-DOM and updates automatically on resize.
 *
 * Give the wrapping element (cell, flex child) `min-width: 0` so the span
 * actually sees a bounded width.
 */
import { useRef } from 'react';
import useFittedText from '../hooks/useFittedText.js';

export default function FittedText({
  text,
  mode = 'end',
  className,
  title: explicitTitle,
  ariaLabel,
}) {
  const ref = useRef(null);
  const fitted = useFittedText(ref, text || '', { mode });
  return (
    <span
      ref={ref}
      className={className}
      title={explicitTitle ?? text ?? undefined}
      aria-label={ariaLabel}
      style={{
        display: 'block',
        minWidth: 0,
        overflow: 'hidden',
        whiteSpace: 'nowrap',
      }}
    >
      {fitted}
    </span>
  );
}
