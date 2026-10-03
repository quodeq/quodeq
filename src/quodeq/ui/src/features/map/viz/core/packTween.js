import { useEffect, useRef, useState } from 'react';

// The SVG view zooms with `transition: transform 0.5s ease`; the canvas
// reproduces that by tweening the focus transform itself.
export const PACK_TWEEN_MS = 500;
const HALF = 0.5;
const CUBIC = 3;
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

/** Cubic ease-in-out on [0, 1]. */
export function easeInOut(t) {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  // Second half mirrors the first: ease out of the remaining distance.
  return t < HALF ? (2 * t) ** CUBIC / 2 : 1 - (2 * (1 - t)) ** CUBIC / 2;
}

/** Interpolate two `{ k, tx, ty }` transforms. */
export function lerpTransform(from, to, t) {
  return {
    k: from.k + (to.k - from.k) * t,
    tx: from.tx + (to.tx - from.tx) * t,
    ty: from.ty + (to.ty - from.ty) * t,
  };
}

function sameTransform(a, b) {
  return a.k === b.k && a.tx === b.tx && a.ty === b.ty;
}

/** Whether the user asked for no motion (also true without matchMedia). */
export function prefersReducedMotion() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true;
  return window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

/**
 * The focus transform as currently displayed: snaps to `target` when
 * `skip.current` is set (first paint, breadcrumb jumps) or under reduced
 * motion, otherwise eases from the previous value over PACK_TWEEN_MS.
 */
export function useTweenedTransform(target, skip) {
  const [shown, setShown] = useState(target);
  const shownRef = useRef(target);

  useEffect(() => {
    const from = shownRef.current;
    // Same values, new object (the root arriving from the worker): adopt it
    // so callers comparing identity see the tween as settled.
    if (sameTransform(from, target) || skip?.current || prefersReducedMotion()) {
      shownRef.current = target;
      setShown(target);
      return undefined;
    }
    let frame = 0;
    const start = performance.now();
    const step = (now) => {
      const t = easeInOut((now - start) / PACK_TWEEN_MS);
      const next = t >= 1 ? target : lerpTransform(from, target, t);
      shownRef.current = next;
      setShown(next);
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, skip]);

  return shown;
}
