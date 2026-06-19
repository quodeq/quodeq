import { useRef } from 'react';

const SEG_LABELS = ['CRITICAL', 'POOR', 'ADEQUATE', 'GOOD', 'EXEMPLARY'];
const GRADE_COLOR_VARS = [
  'var(--color-grade-bottom-text)', 'var(--color-grade-low-text)',
  'var(--color-grade-mid-text)', 'var(--color-grade-high-text)',
  'var(--color-grade-top-text)',
];
const MIN_GAP = 0.5;

/**
 * Segmented 0-10 bar; thresholds = [[9,'Exemplary'],[7,..],[5,..],[3,..]]
 * (descending). Dragging divider i moves the ascending boundary i.
 * onChange receives a full new thresholds array (descending, labels preserved).
 */
export default function GradeBoundaryBar({ thresholds = [], onChange }) {
  const barRef = useRef(null);
  // ascending boundary values, e.g. [3,5,7,9]
  const asc = [...thresholds].map(([t]) => t).reverse();
  const edges = [0, ...asc, 10];

  // Keep the latest ascending values in a ref so the pointermove closure reads
  // fresh clamps across re-renders during one continuous drag (avoids stale-closure
  // clamps from the asc captured at the drag's start).
  const ascRef = useRef(asc);
  ascRef.current = asc;

  const startDrag = (dividerIdx) => (downEvent) => {
    if (downEvent.currentTarget.closest('fieldset[disabled]')) return;
    downEvent.preventDefault();
    const rect = barRef.current.getBoundingClientRect();
    const move = (e) => {
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const live = ascRef.current;
      let value = ((clientX - rect.left) / rect.width) * 10;
      const lo = (dividerIdx === 0 ? 0 : live[dividerIdx - 1]) + MIN_GAP;
      const hi = (dividerIdx === live.length - 1 ? 10 : live[dividerIdx + 1]) - MIN_GAP;
      value = Math.round(Math.min(hi, Math.max(lo, value)) * 10) / 10;
      const nextAsc = [...live];
      nextAsc[dividerIdx] = value;
      const desc = [...nextAsc].reverse();
      onChange(thresholds.map(([, label], i) => [desc[i], label]));
    };
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
  };

  const stepKey = (dividerIdx, delta) => {
    const live = ascRef.current;
    const lo = (dividerIdx === 0 ? 0 : live[dividerIdx - 1]) + MIN_GAP;
    const hi = (dividerIdx === live.length - 1 ? 10 : live[dividerIdx + 1]) - MIN_GAP;
    const next = Math.round(Math.min(hi, Math.max(lo, live[dividerIdx] + delta)) * 10) / 10;
    if (next === live[dividerIdx]) return;
    const nextAsc = [...live];
    nextAsc[dividerIdx] = next;
    const desc = [...nextAsc].reverse();
    onChange(thresholds.map(([, label], i) => [desc[i], label]));
  };

  return (
    <div>
      <div className="gf-boundary-bar" ref={barRef}>
        {edges.slice(0, -1).map((edge, i) => (
          <Segment
            key={SEG_LABELS[i]}
            i={i}
            width={edges[i + 1] - edge}
            hasDivider={i < asc.length}
            dividerValue={asc[i]}
            onDrag={startDrag}
            onStepKey={stepKey}
          />
        ))}
      </div>
      <div className="gf-boundary-ticks">
        {edges.slice(0, -1).map((edge, i) => (
          <span key={`tick${i}`} style={{ flex: edges[i + 1] - edge }}>{edge}</span>
        ))}
        <span>10</span>
      </div>
    </div>
  );
}

function Segment({ i, width, hasDivider, dividerValue, onDrag, onStepKey }) {
  return (
    <>
      <div
        className="gf-boundary-seg"
        style={{ flex: width, background: GRADE_COLOR_VARS[i] }}
      >
        {SEG_LABELS[i]}
      </div>
      {hasDivider ? (
        <div
          className="gf-boundary-divider"
          role="slider"
          aria-label={`Boundary ${i + 1}`}
          aria-valuemin={0}
          aria-valuemax={10}
          aria-valuenow={dividerValue}
          tabIndex={0}
          onPointerDown={onDrag(i)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowRight' || e.key === 'ArrowUp') { e.preventDefault(); onStepKey(i, MIN_GAP); }
            else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') { e.preventDefault(); onStepKey(i, -MIN_GAP); }
          }}
        />
      ) : null}
    </>
  );
}
