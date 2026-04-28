import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSidePane } from './SidePaneContext.jsx';
import { SidePaneWindow } from './SidePaneWindow.jsx';
import { clampSidePaneWidth } from './paneWidthMath.js';
import './SidePane.css';

const MIN_WINDOW_RATIO = 0.1;

export function SidePane() {
  const { windows, isOpen, paneWidth, setPaneWidth, removeWindow } = useSidePane();

  // Per-resizer ratios: ratios[i] in [0,1] is the share of (weights[i] + weights[i+1])
  // that goes to weights[i]. Reset whenever the window count changes (structural reset).
  const [ratios, setRatios] = useState(() => Array(Math.max(0, windows.length - 1)).fill(0.5));
  useEffect(() => {
    setRatios(Array(Math.max(0, windows.length - 1)).fill(0.5));
  }, [windows.length]);

  // Outer pane (left-edge) drag — resizes the whole dock width.
  const [isDragging, setIsDragging] = useState(false);
  const onOuterDividerPointerDown = useCallback((e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = paneWidth;
    const viewport = window.innerWidth;
    setIsDragging(true);
    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    const onMove = (ev) => {
      const delta = startX - ev.clientX;
      const next = clampSidePaneWidth(startWidth + delta, viewport);
      document.documentElement.style.setProperty('--side-pane-width', `${next}px`);
    };
    const onUp = (ev) => {
      const delta = startX - ev.clientX;
      setPaneWidth(clampSidePaneWidth(startWidth + delta, window.innerWidth));
      setIsDragging(false);
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [paneWidth, setPaneWidth]);

  // Internal between-window resizer. Mutates the two adjacent slot
  // elements' inline flex grow factors directly during the drag (no
  // setState — same trick as the outer drag with --side-pane-width)
  // so the markdown bodies don't re-render every pointer move. Commits
  // the final ratio to React state on release.
  const containerRef = useRef(null);
  const onInnerDividerPointerDown = useCallback((index) => (e) => {
    e.preventDefault();
    const container = containerRef.current;
    if (!container) return;
    const slots = container.querySelectorAll('.side-pane-window-slot');
    const aEl = slots[index];
    const bEl = slots[index + 1];
    if (!aEl || !bEl) return;
    const startY = e.clientY;
    const startRatio = ratios[index] ?? 0.5;
    const span = aEl.offsetHeight + bEl.offsetHeight;
    if (span <= 0) return;
    // Combined weight of these two slots stays constant during this drag —
    // we just split it differently. Capture it once.
    const aStartFlex = parseFloat(aEl.style.flexGrow) || 1;
    const bStartFlex = parseFloat(bEl.style.flexGrow) || 1;
    const combinedFlex = aStartFlex + bStartFlex;
    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    let pendingRatio = startRatio;
    let rafId = null;
    const apply = () => {
      rafId = null;
      aEl.style.flex = `${combinedFlex * pendingRatio} 1 0`;
      bEl.style.flex = `${combinedFlex * (1 - pendingRatio)} 1 0`;
    };
    const onMove = (ev) => {
      const delta = ev.clientY - startY;
      pendingRatio = Math.min(1 - MIN_WINDOW_RATIO, Math.max(MIN_WINDOW_RATIO, startRatio + delta / span));
      if (rafId == null) rafId = requestAnimationFrame(apply);
    };
    const onUp = () => {
      if (rafId != null) cancelAnimationFrame(rafId);
      apply();
      setRatios((prev) => {
        const out = [...prev];
        out[index] = pendingRatio;
        return out;
      });
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [ratios]);

  if (!isOpen) return null;

  // Build weights from ratios: walk through, treating each ratios[i] as the
  // split between weights[i] and weights[i+1] of their combined share.
  const weights = Array(windows.length).fill(1);
  for (let i = 0; i < ratios.length; i += 1) {
    const r = ratios[i] ?? 0.5;
    const sum = weights[i] + weights[i + 1];
    weights[i] = sum * r;
    weights[i + 1] = sum * (1 - r);
  }

  return (
    <aside
      className="side-pane"
      role="complementary"
      aria-label="Side pane"
      ref={containerRef}
    >
      <div
        className={`side-pane__divider${isDragging ? ' side-pane__divider--dragging' : ''}`}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize side pane"
        onPointerDown={onOuterDividerPointerDown}
      />
      {windows.map((spec, i) => (
        <React.Fragment key={spec.id}>
          <div className="side-pane-window-slot" style={{ flex: `${weights[i]} 1 0` }}>
            <SidePaneWindow spec={spec} onClose={removeWindow} />
          </div>
          {i < windows.length - 1 && (
            <div
              className="side-pane__row-divider"
              role="separator"
              aria-orientation="horizontal"
              aria-label={`Resize between window ${i + 1} and ${i + 2}`}
              onPointerDown={onInnerDividerPointerDown(i)}
            />
          )}
        </React.Fragment>
      ))}
    </aside>
  );
}
