/**
 * An empty-space click first backs out of the innermost zoom or focus: a
 * zoomed file (with its zoom target), else a zoom target, else a focused
 * folder. Each backs out with an animated transition and a saved nav state.
 */
import { describe, it, expect, vi } from 'vitest';

vi.mock('../core/galaxyCore.js', () => ({ getThemeColors: () => ({ gradeMid: { r: 1, g: 2, b: 3 } }) }));
vi.mock('./galaxyFolderScene.js', () => ({ buildFolderScene: vi.fn(() => ({})) }));

import { handleEmptySpaceClick } from './galaxyFolderClickHandlers.js';

function click(state) {
  const refs = {
    zoomedFileRef: { current: state.zoomedFile ?? null },
    zoomTargetRef: { current: state.zoomTarget ?? null },
    focusedFolderRef: { current: state.focusedFolder ?? null },
    flyRef: { current: null },
    mouseRef: { current: { x: -1, y: -1 } },
  };
  const calls = [];
  handleEmptySpaceClick(refs, { path: [{}, {}] }, {
    startTransition: (animated) => calls.push(`transition:${animated}`),
    saveNav: () => calls.push('save'),
    getFitZoom: () => 1, scene: {}, size: { w: 1, h: 1 },
  });
  return { left: [refs.zoomedFileRef.current, refs.zoomTargetRef.current, refs.focusedFolderRef.current], calls };
}

describe('handleEmptySpaceClick backing out of a zoom or focus', () => {
  it('drops a zoomed file together with its zoom target, keeping the focused folder', () => {
    expect(click({ zoomedFile: 'f', zoomTarget: 't', focusedFolder: 'd' }))
      .toEqual({ left: [null, null, 'd'], calls: ['transition:true', 'save'] });
  });

  it('drops a zoom target before a focused folder', () => {
    expect(click({ zoomTarget: 't', focusedFolder: 'd' }))
      .toEqual({ left: [null, null, 'd'], calls: ['transition:true', 'save'] });
  });

  it('drops a focused folder when nothing is zoomed', () => {
    expect(click({ focusedFolder: 'd' }))
      .toEqual({ left: [null, null, null], calls: ['transition:true', 'save'] });
  });
});
