/**
 * Canvas box size, observed from the canvas's parent element.
 *
 * Both galaxy canvases size themselves to their container rather than to a
 * fixed attribute, so both need the same ResizeObserver. It lives here so
 * neither view model has to import the other.
 */
import { useEffect, useState } from 'react';
import { DEFAULT_CANVAS_W, DEFAULT_CANVAS_H } from '../core/galaxyTunables.js';

/**
 * Track the canvas parent's content box.
 *
 * Starts at the default canvas size so the first scene can be laid out before
 * the observer reports, and ignores zero-sized boxes (a hidden tab) so a
 * collapsed container never wipes a valid layout.
 *
 * @param {{current: HTMLCanvasElement|null}} canvasRef
 * @returns {{w: number, h: number}}
 */
export function useCanvasSize(canvasRef) {
  const [size, setSize] = useState({ w: DEFAULT_CANVAS_W, h: DEFAULT_CANVAS_H });
  useEffect(() => {
    const el = canvasRef.current?.parentElement;
    if (!el) return undefined;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return size;
}
