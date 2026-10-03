import { vi } from 'vitest';

/** A 2D canvas context of spies, enough for the Map canvas renderers. */
export function fakeCanvasContext() {
  return {
    clearRect: vi.fn(), beginPath: vi.fn(), closePath: vi.fn(), arc: vi.fn(), fill: vi.fn(), stroke: vi.fn(),
    fillText: vi.fn(), setTransform: vi.fn(), save: vi.fn(), restore: vi.fn(), translate: vi.fn(), scale: vi.fn(),
    moveTo: vi.fn(), lineTo: vi.fn(), quadraticCurveTo: vi.fn(),
    fillStyle: '', strokeStyle: '', globalAlpha: 1, lineWidth: 1, font: '', textAlign: '', textBaseline: '',
    shadowBlur: 0, shadowColor: '',
  };
}
