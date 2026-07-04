import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import GalaxyView from './GalaxyView.jsx';

// GalaxyView wires a ResizeObserver in a useEffect; jsdom does not provide one.
// Stub it so the test exercises the real render path and isolates the bug under
// test (a missing/null `dimensions` prop) rather than the environment gap.
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
});
afterEach(() => { vi.unstubAllGlobals(); });

describe('GalaxyView', () => {
  it('does not crash when dimensions is omitted', () => {
    expect(() => render(<GalaxyView onNavigate={() => {}} />)).not.toThrow();
  });

  it('does not crash when dimensions is null', () => {
    expect(() => render(<GalaxyView dimensions={null} onNavigate={() => {}} />)).not.toThrow();
  });
});
