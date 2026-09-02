import React from 'react';
import { useSidePane } from './SidePaneContext.jsx';
import { SidePaneWindow } from './SidePaneWindow.jsx';
import { clampSidePaneWidth } from './paneWidthMath.js';
import { t } from '../../strings/index.js';
import { useOuterPaneDrag } from './hooks/useOuterPaneDrag.js';
import { useInnerDividerDrag, MIN_WINDOW_RATIO } from './hooks/useInnerDividerDrag.js';
import './SidePane.css';

// Build weights from ratios: walk through, treating each ratios[i] as the
// split between weights[i] and weights[i+1] of their combined share.
function computeWeights(windowCount, ratios) {
  const weights = Array(windowCount).fill(1);
  for (let i = 0; i < ratios.length; i += 1) {
    const r = ratios[i] ?? 0.5;
    const sum = weights[i] + weights[i + 1];
    weights[i] = sum * r;
    weights[i + 1] = sum * (1 - r);
  }
  return weights;
}

function OuterDivider({ isDragging, onOuterDividerPointerDown, paneWidth, setPaneWidth }) {
  return (
    <div
      className={`side-pane__divider${isDragging ? ' side-pane__divider--dragging' : ''}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={t('sidePane.resize')}
      tabIndex={0}
      onPointerDown={onOuterDividerPointerDown}
      onKeyDown={(e) => {
        const STEP = 16;
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          e.preventDefault();
          const delta = e.key === 'ArrowLeft' ? -STEP : STEP;
          const newWidth = clampSidePaneWidth(paneWidth + delta, window.innerWidth);
          document.documentElement.style.setProperty('--side-pane-width', `${newWidth}px`);
          setPaneWidth(newWidth);
        }
      }}
    />
  );
}

function InnerRowDivider({ i, windowCount, ratios, setRatios, onInnerDividerPointerDown }) {
  if (i >= windowCount - 1) return null;
  return (
    <div
      className="side-pane__row-divider"
      role="separator"
      aria-orientation="horizontal"
      aria-label={t('sidePane.resizeBetween', { first: i + 1, second: i + 2 })}
      aria-valuenow={Math.round((ratios[i] ?? 0.5) * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
      tabIndex={0}
      onPointerDown={onInnerDividerPointerDown(i)}
      onKeyDown={(e) => {
        const STEP = 0.05;
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
          e.preventDefault();
          const delta = e.key === 'ArrowUp' ? -STEP : STEP;
          setRatios((prev) => {
            const out = [...prev];
            out[i] = Math.min(1 - MIN_WINDOW_RATIO, Math.max(MIN_WINDOW_RATIO, (out[i] ?? 0.5) + delta));
            return out;
          });
        }
      }}
    />
  );
}

export function SidePane() {
  const { windows, isOpen, paneWidth, setPaneWidth, removeWindow } = useSidePane();

  // Outer pane (left-edge) drag, plus the shared drag plumbing (container
  // ref, resizing flag, active-drag cleanup ref) — see hooks/useOuterPaneDrag.js.
  const {
    containerRef, setResizingFlag, activeDragCleanupRef, isDragging, onOuterDividerPointerDown,
  } = useOuterPaneDrag({ paneWidth, setPaneWidth });

  // Internal between-window resizer, plus the per-resizer ratios state —
  // see hooks/useInnerDividerDrag.js.
  const { ratios, setRatios, onInnerDividerPointerDown } = useInnerDividerDrag({
    windowCount: windows.length, containerRef, setResizingFlag, activeDragCleanupRef,
  });

  if (!isOpen) return null;

  const weights = computeWeights(windows.length, ratios);

  return (
    <aside
      className="side-pane"
      role="complementary"
      aria-label={t('sidePane.aria')}
      ref={containerRef}
    >
      <OuterDivider isDragging={isDragging} onOuterDividerPointerDown={onOuterDividerPointerDown} paneWidth={paneWidth} setPaneWidth={setPaneWidth} />
      {windows.map((spec, i) => (
        <React.Fragment key={spec.id}>
          <div className="side-pane-window-slot" style={{ flex: `${weights[i]} 1 0` }}>
            <SidePaneWindow spec={spec} onClose={removeWindow} />
          </div>
          <InnerRowDivider i={i} windowCount={windows.length} ratios={ratios} setRatios={setRatios} onInnerDividerPointerDown={onInnerDividerPointerDown} />
        </React.Fragment>
      ))}
    </aside>
  );
}
