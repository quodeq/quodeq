// Post-PR review M7: the legacy-key migration runs inside the useState
// initializer, i.e. during render. Its persist-error callback used to call
// showToast right there, and showToast sets state in SidePaneContext, so
// React logged "Cannot update a component while rendering a different
// component". The toast must fire from an effect after mount, once.
//
// Own file: useProviderSettings.test.jsx sits at the 300-line cap.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { useState } from 'react';
import { renderHook } from '@testing-library/react';
import useProviderSettings from './useProviderSettings.js';

const showToast = vi.fn();
vi.mock('../../side-pane/SidePaneContext.jsx', () => ({
  useSidePane: () => ({ showToast }),
}));

vi.mock('../../../api/providers.js', () => ({
  saveProviderKey: vi.fn(),
}));

describe('useProviderSettings legacy-migration persist failure', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    showToast.mockReset();
  });

  it('toasts after mount, not during render, and only once', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    let setOuter;
    function Wrapper({ children }) {
      const [, set] = useState(0);
      setOuter = set;
      return children;
    }
    // A showToast that behaves like the real one: it updates another component.
    showToast.mockImplementation(() => setOuter((n) => n + 1));
    const storage = {
      // Only the legacy key has a value, so loadProviderState migrates it...
      getItem: vi.fn((key) => (String(key).includes('pool-budget') ? '600' : null)),
      // ...and the migration write fails.
      setItem: vi.fn(() => { throw new DOMException('QuotaExceededError'); }),
      removeItem: vi.fn(),
    };

    const { rerender } = renderHook(
      () => useProviderSettings('ollama', {}, { storage }),
      { wrapper: Wrapper },
    );

    expect(showToast).toHaveBeenCalledTimes(1);
    const logged = errorSpy.mock.calls.flat().map(String).join('\n');
    expect(logged).not.toMatch(/Cannot update a component/);

    // A later render must not toast again: it is a one-shot mount effect.
    rerender();
    expect(showToast).toHaveBeenCalledTimes(1);
  });
});
