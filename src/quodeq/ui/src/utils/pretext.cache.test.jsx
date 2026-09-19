import { describe, it, expect, vi, beforeEach } from 'vitest';

// The real package needs a canvas; this suite is about the module's own FIFO
// caches, so the measurement calls are stubbed and counted instead.
const prepareCalls = [];
const segmentCalls = [];

vi.mock('@chenglou/pretext', () => ({
  prepare: (text, font) => { prepareCalls.push([text, font]); return { text, font }; },
  prepareWithSegments: (text, font) => { segmentCalls.push([text, font]); return { text, font }; },
  layout: () => ({ height: 0, lineCount: 0 }),
  measureNaturalWidth: (prepared) => prepared.text.length,
}));

const { prepare, measureWidth, clearPrepareCache } = await import('./pretext.js');

const FONT = '13px mono';

describe('pretext prepare cache', () => {
  beforeEach(() => {
    clearPrepareCache();
    prepareCalls.length = 0;
    segmentCalls.length = 0;
  });

  it('reuses the prepared text for an identical (text, font) pair', () => {
    const first = prepare('hello', FONT);
    expect(prepare('hello', FONT)).toBe(first);
    expect(prepareCalls).toHaveLength(1);
  });

  it('evicts the oldest entry once the cache is full, keeping the newest', () => {
    const LIMIT = 1024;
    for (let i = 0; i < LIMIT; i++) prepare(`t${i}`, FONT);
    expect(prepareCalls).toHaveLength(LIMIT);

    // One past the cap: the newcomer lands, the oldest key is dropped.
    prepare('overflow', FONT);
    expect(prepareCalls).toHaveLength(LIMIT + 1);

    prepare('t0', FONT);
    expect(prepareCalls).toHaveLength(LIMIT + 2); // t0 was evicted, recomputed

    prepare('overflow', FONT);
    prepare(`t${LIMIT - 1}`, FONT);
    expect(prepareCalls).toHaveLength(LIMIT + 2); // both still cached
  });

  // The suite's beforeEach relies on this: if the clear missed the segment
  // cache, the measureWidth tests below would depend on running first.
  it('clearPrepareCache empties the segment cache too, not just the prepare cache', () => {
    prepare('shared', FONT);
    measureWidth('shared', FONT);
    expect(prepareCalls).toHaveLength(1);
    expect(segmentCalls).toHaveLength(1);

    clearPrepareCache();

    prepare('shared', FONT);
    measureWidth('shared', FONT);
    expect(prepareCalls).toHaveLength(2);
    expect(segmentCalls).toHaveLength(2);
  });

  it('caches segment preparation for measureWidth under the same policy', () => {
    const LIMIT = 512;
    for (let i = 0; i < LIMIT; i++) measureWidth(`s${i}`, FONT);
    expect(segmentCalls).toHaveLength(LIMIT);

    measureWidth('s0', FONT);
    expect(segmentCalls).toHaveLength(LIMIT); // still cached

    measureWidth('spill', FONT);
    measureWidth('s0', FONT);
    expect(segmentCalls).toHaveLength(LIMIT + 2); // s0 evicted by 'spill'
  });
});
