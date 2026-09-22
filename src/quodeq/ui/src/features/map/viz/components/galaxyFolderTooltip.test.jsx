import { describe, test, expect, vi } from 'vitest';
import { createTooltipUpdater } from './galaxyFolderTooltip.js';
import * as galaxyFolderScene from './galaxyFolderScene.js';

function makeRefs(node) {
  const el = { style: {}, innerHTML: '' };
  return {
    tooltipRef: { current: el },
    hoveredRef: { current: { type: 'folder', data: { _node: node, complianceRate: 1, violations: 0, severity: {}, col: [0, 0, 0], name: 'x' }, starIdx: 0 } },
    animRef: { current: false },
    focusedFolderRef: { current: null },
  };
}

describe('createTooltipUpdater', () => {
  test('countDescendants is memoized per node across repeated mousemove-driven updates', () => {
    const node = { children: [{ children: [] }, { children: [] }] };
    const spy = vi.spyOn(galaxyFolderScene, 'countDescendants');
    const refs = makeRefs(node);
    const updateTooltip = createTooltipUpdater(refs);

    updateTooltip(10, 10);
    updateTooltip(11, 11);
    updateTooltip(12, 12);

    expect(spy).toHaveBeenCalledTimes(1);
  });
});
