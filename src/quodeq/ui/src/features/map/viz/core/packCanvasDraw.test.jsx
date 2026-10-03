import { describe, it, expect, vi } from 'vitest';
import { fakeCanvasContext } from '../../../../test-utils/fakeCanvasContext.js';
import { drawPack, makeColorResolver } from './packCanvasDraw.js';
import { packViewport } from './packCanvasGeometry.js';
import { PACK_BASE_SIZE } from './packLayout.js';


const style = { getPropertyValue: (name) => ({ '--color-sev-major-text': '#f80', '--color-border': '#333' }[name] || '') };

describe('makeColorResolver', () => {
  it('resolves css variables through the style and passes plain colours through', () => {
    const style2 = { getPropertyValue: vi.fn(style.getPropertyValue) };
    const color = makeColorResolver(style2);
    expect(color('var(--color-sev-major-text)')).toBe('#f80');
    expect(color('var(--color-sev-major-text)')).toBe('#f80');
    expect(style2.getPropertyValue).toHaveBeenCalledTimes(1);
    expect(color('#abc')).toBe('#abc');
    expect(color('var(--missing)')).toBe('var(--missing)');
  });
});

describe('drawPack', () => {
  const root = { depth: 0, data: { name: '/', path: '', isFile: false, severity: {}, children: [1] } };
  const folder = { depth: 1, parent: root, data: { name: 'src', path: 'src', isFile: false, severity: { major: 1 }, children: [1] } };
  const file = { depth: 2, parent: folder, data: { name: 'a.py', path: 'src/a.py', isFile: true, severity: { major: 1 } } };
  const circles = [root, folder, file];
  const viewport = packViewport(PACK_BASE_SIZE, PACK_BASE_SIZE);

  it('draws every visible circle and labels the focused level', () => {
    const ctx = fakeCanvasContext();
    const coords = [{ cx: 300, cy: 300, r: 300 }, { cx: 300, cy: 300, r: 150 }, { cx: 300, cy: 300, r: 50 }];
    const drawn = drawPack(ctx, { circles, screenCoords: coords, viewport, viewMode: 'violations', hover: null, focusNode: root, showLabels: true, style, width: 600, height: 600 });
    expect(drawn).toBe(3);
    expect(ctx.arc).toHaveBeenCalledTimes(2);
    expect(ctx.quadraticCurveTo).toHaveBeenCalled();
    expect(ctx.fillText).toHaveBeenCalledTimes(1);
    expect(ctx.fillText.mock.calls[0][0]).toBe('src');
  });

  it('culls offscreen circles but keeps sub-pixel ones', () => {
    const ctx = fakeCanvasContext();
    const coords = [{ cx: 300, cy: 300, r: 300 }, { cx: -900, cy: 300, r: 150 }, { cx: 300, cy: 300, r: 0.1 }];
    const drawn = drawPack(ctx, { circles, screenCoords: coords, viewport, viewMode: 'violations', hover: null, focusNode: root, showLabels: false, style, width: 600, height: 600 });
    expect(drawn).toBe(2);
    expect(ctx.fillText).not.toHaveBeenCalled();
  });
});
