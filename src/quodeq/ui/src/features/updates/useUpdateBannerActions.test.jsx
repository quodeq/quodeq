import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { ApiProvider } from '../../api/ApiContext.jsx';
import { useUpdateBannerActions } from './useUpdateBannerActions.js';

function wrapper(api) {
  return function Wrapper({ children }) {
    return <ApiProvider value={api}>{children}</ApiProvider>;
  };
}

describe('useUpdateBannerActions', () => {
  it('returns markUpdateDisclosed and dismissUpdate from the injected ApiContext', () => {
    const markUpdateDisclosed = vi.fn();
    const dismissUpdate = vi.fn();
    const { result } = renderHook(() => useUpdateBannerActions(), {
      wrapper: wrapper({ markUpdateDisclosed, dismissUpdate }),
    });
    expect(result.current.markUpdateDisclosed).toBe(markUpdateDisclosed);
    expect(result.current.dismissUpdate).toBe(dismissUpdate);
  });
});
