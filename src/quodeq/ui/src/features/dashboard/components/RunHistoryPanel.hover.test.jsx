import { describe, it, expect, vi } from 'vitest';
import { hoverWithPrefetch } from './RunHistoryPanel.jsx';

const DATA = [{ runId: 'r1' }, { runId: 'r2' }, { }];

describe('hoverWithPrefetch', () => {
  it('sets the index and warms the hovered run', () => {
    const setIndex = vi.fn();
    const onHover = vi.fn();
    const onEnd = vi.fn();
    hoverWithPrefetch(setIndex, DATA, onHover, onEnd)(1);
    expect(setIndex).toHaveBeenCalledWith(1);
    expect(onHover).toHaveBeenCalledWith('r2');
    expect(onEnd).not.toHaveBeenCalled();
  });

  it('cancels the warm-up when the pointer leaves the chart', () => {
    const setIndex = vi.fn();
    const onHover = vi.fn();
    const onEnd = vi.fn();
    hoverWithPrefetch(setIndex, DATA, onHover, onEnd)(null);
    expect(setIndex).toHaveBeenCalledWith(null);
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(onHover).not.toHaveBeenCalled();
  });

  it('skips buckets without a run id and tolerates missing callbacks', () => {
    const setIndex = vi.fn();
    const onHover = vi.fn();
    hoverWithPrefetch(setIndex, DATA, onHover, undefined)(2);
    expect(onHover).not.toHaveBeenCalled();
    expect(() => hoverWithPrefetch(setIndex, DATA, undefined, undefined)(null)).not.toThrow();
  });
});
