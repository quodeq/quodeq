import { describe, it, expect } from 'vitest';
import { drawConstellationLines } from './galaxyFolderDraw.js';

function recordingCtx() {
  const log = [];
  const ctx = {};
  for (const m of ['beginPath', 'moveTo', 'lineTo', 'stroke']) ctx[m] = (...a) => log.push([m, ...a]);
  return { ctx, log };
}

const tc = { textMuted: { r: 1, g: 2, b: 3 } };
const w2s = (x, y) => ({ x, y });
const stars = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }];

describe('drawConstellationLines', () => {
  it('draws every line in one path with one stroke', () => {
    const { ctx, log } = recordingCtx();
    const scene = { rootStars: stars, lines: [{ a: 0, b: 1 }, { a: 1, b: 2 }, { a: 2, b: 3 }] };
    drawConstellationLines(ctx, scene, tc, w2s);
    const count = (m) => log.filter(([name]) => name === m).length;
    expect(count('beginPath')).toBe(1);
    expect(count('moveTo')).toBe(3);
    expect(count('lineTo')).toBe(3);
    expect(count('stroke')).toBe(1);
    expect(ctx.strokeStyle).toBe('rgba(1,2,3,0.25)');
    expect(ctx.lineWidth).toBe(0.8);
  });

  it('touches nothing when there are no lines', () => {
    const { ctx, log } = recordingCtx();
    drawConstellationLines(ctx, { rootStars: stars, lines: [] }, tc, w2s);
    expect(log).toEqual([]);
  });
});
