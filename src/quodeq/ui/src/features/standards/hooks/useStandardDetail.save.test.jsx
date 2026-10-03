import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useStandardDetail } from './useStandardDetail.js';

const STORED = { id: 'accessibility', name: 'Accessibility', type: 'custom', managed: false, principles: [] };

function makeWrapper(api) {
  return function Wrapper({ children }) {
    return <ApiProvider value={api}>{children}</ApiProvider>;
  };
}

// The editor's commit flow decides whether to leave the page from save()'s
// return value, so a failed PUT must come back as { error }, not vanish into
// hook state only.
describe('useStandardDetail save', () => {
  it('returns the API error when the update is rejected', async () => {
    const api = {
      getStandard: vi.fn(async () => STORED),
      createStandard: vi.fn(),
      updateStandard: vi.fn(async () => { throw new Error('Standard not found: accessibility-v2'); }),
    };
    const { result } = renderHook(() => useStandardDetail('accessibility', false), { wrapper: makeWrapper(api) });
    await waitFor(() => expect(result.current.standard).not.toBeNull());

    let outcome;
    await act(async () => { outcome = await result.current.save(); });

    expect(outcome).toEqual({ error: 'Standard not found: accessibility-v2' });
    expect(result.current.error).toBe('Standard not found: accessibility-v2');
  });

  it('returns no error when the update succeeds', async () => {
    const api = {
      getStandard: vi.fn(async () => STORED),
      createStandard: vi.fn(),
      updateStandard: vi.fn(async () => STORED),
    };
    const { result } = renderHook(() => useStandardDetail('accessibility', false), { wrapper: makeWrapper(api) });
    await waitFor(() => expect(result.current.standard).not.toBeNull());

    let outcome;
    await act(async () => { outcome = await result.current.save(); });

    expect(outcome).toEqual({ error: null });
    expect(api.updateStandard).toHaveBeenCalledWith('accessibility', STORED);
  });
});
