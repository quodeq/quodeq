import { describe, it, expect, vi } from 'vitest';
import { render, renderHook, fireEvent } from '@testing-library/react';
import GalaxyCanvas, { useFadeIn } from './GalaxyCanvas.jsx';

describe('useFadeIn', () => {
  it('stays hidden until the view is ready', () => {
    const { result } = renderHook(({ ready }) => useFadeIn(ready), { initialProps: { ready: false } });
    expect(result.current).toBe(false);
  });

  it('turns visible once ready and stays visible if readiness drops', () => {
    const { result, rerender } = renderHook(({ ready }) => useFadeIn(ready), { initialProps: { ready: true } });
    rerender({ ready: false });
    expect(result.current).toBe(true);
  });
});

describe('GalaxyCanvas', () => {
  it('fades the frame by visibility and labels the canvas as an application', () => {
    const { container } = render(
      <GalaxyCanvas visible={false} size={{ w: 10, h: 20 }} label="Galaxy" handlers={{}}><p>child</p></GalaxyCanvas>,
    );
    const canvas = container.querySelector('canvas[role="application"][aria-label="Galaxy"]');
    expect([container.firstChild.style.opacity, canvas.width, canvas.height, container.querySelector('p').textContent])
      .toEqual(['0', 10, 20, 'child']);
  });

  it('routes the canvas events to the given handlers', () => {
    const handlers = { handleClick: vi.fn(), handleKeyDown: vi.fn(), handleFocus: vi.fn() };
    const { container } = render(<GalaxyCanvas visible size={{ w: 1, h: 1 }} label="G" handlers={handlers} />);
    const canvas = container.querySelector('canvas');
    fireEvent.click(canvas);
    fireEvent.keyDown(canvas, { key: 'Enter' });
    fireEvent.focus(canvas);
    expect([handlers.handleClick.mock.calls.length, handlers.handleKeyDown.mock.calls.length, handlers.handleFocus.mock.calls.length])
      .toEqual([1, 1, 1]);
  });
});
