import { describe, it, expect } from 'vitest';
import { fakeCanvasContext } from '../../../../test-utils/fakeCanvasContext.js';
import { drawFileIcon } from './packCanvasFile.js';
import { FILE_SHAPE_BASE, FILE_RULE_LINES } from './fileShapeGeometry.js';

const R_PX = 20;
const LARGE = { px: 100, py: 80, rPx: R_PX, fill: '#f80', stroke: '#333', glow: 0 };

describe('drawFileIcon', () => {
  it('traces the page at the circle centre, scaled to its radius', () => {
    const ctx = fakeCanvasContext();
    drawFileIcon(ctx, LARGE);
    expect(ctx.translate).toHaveBeenCalledWith(100, 80);
    const s = R_PX / (FILE_SHAPE_BASE / 2);
    expect(ctx.scale).toHaveBeenCalledWith(s, s);
    expect(ctx.quadraticCurveTo).toHaveBeenCalledTimes(3);
    expect(ctx.arc).not.toHaveBeenCalled();
    expect(ctx.restore).toHaveBeenCalled();
  });

  it('draws the fold and rule lines only when the icon is big enough to show them', () => {
    const big = fakeCanvasContext();
    drawFileIcon(big, LARGE);
    // body + fold + one path per rule line
    expect(big.beginPath).toHaveBeenCalledTimes(2 + FILE_RULE_LINES.length);

    const tiny = fakeCanvasContext();
    drawFileIcon(tiny, { ...LARGE, rPx: 1 });
    expect(tiny.beginPath).toHaveBeenCalledTimes(1);
  });

  it('glows in the stroke colour when hovered and clears the shadow after', () => {
    const ctx = fakeCanvasContext();
    const seen = [];
    Object.defineProperty(ctx, 'shadowBlur', { set: (v) => seen.push(v), get: () => seen.at(-1) ?? 0 });
    drawFileIcon(ctx, { ...LARGE, glow: 6 });
    expect(seen[0]).toBeGreaterThan(0);
    expect(ctx.shadowColor).toBe('#333');
    expect(seen.at(-1)).toBe(0);
  });
});
