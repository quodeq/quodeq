import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import React from 'react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useWorkspaceDiff } from './useWorkspaceDiff.js';

describe('useWorkspaceDiff API injection', () => {
  it('uses fetchAssistantWorkspaceDiff from the injected ApiProvider, not a static import', () => {
    const fetchAssistantWorkspaceDiff = vi.fn().mockResolvedValue({ files: [] });
    const apiValue = {
      applyAssistantWorkspace: vi.fn(), createAssistantWorkspacePr: vi.fn(),
      discardAssistantWorkspace: vi.fn(), fetchAssistantWorkspaceDiff,
    };
    renderHook(() => useWorkspaceDiff({ sessionId: 's1' }), {
      wrapper: ({ children }) => <ApiProvider value={apiValue}>{children}</ApiProvider>,
    });
    // useWorkspaceDiff fetches the diff on mount via useEffect(() => loadDiff(), [loadDiff]).
    expect(fetchAssistantWorkspaceDiff).toHaveBeenCalledWith('s1');
  });
});
