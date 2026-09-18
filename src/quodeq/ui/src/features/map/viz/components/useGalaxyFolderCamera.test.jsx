import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useGalaxyFolderCamera } from './useGalaxyFolderCamera.js';

function makeRefs(canvas) {
  return {
    canvasRef: { current: canvas },
    camRef: { current: null },
    flyRef: { current: null },
    sceneRef: { current: null },
    navRef: { current: { path: [] } },
    mouseRef: { current: { x: -1, y: -1 } },
    hoveredRef: { current: null },
    frameRef: { current: null },
    focusedFolderRef: { current: null },
    zoomedFileRef: { current: null },
    zoomTargetRef: { current: null },
    animRef: { current: null },
  };
}

describe('useGalaxyFolderCamera — null 2D context guard', () => {
  it('does not throw and does not start the animation loop when getContext("2d") returns null', () => {
    const rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation(() => 1);
    const cancelSpy = vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {});
    try {
      const canvas = { getContext: vi.fn(() => null) };
      const refs = makeRefs(canvas);
      const scene = { rootStars: [], _maxExtent: 100 };

      expect(() => {
        renderHook(() =>
          useGalaxyFolderCamera({ refs, scene, showLabels: false, saveNav: vi.fn(), setNavVersion: vi.fn() })
        );
      }).not.toThrow();

      expect(rafSpy).not.toHaveBeenCalled();
    } finally {
      rafSpy.mockRestore();
      cancelSpy.mockRestore();
    }
  });
});
