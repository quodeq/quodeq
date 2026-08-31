import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ApiProvider } from '../../api/ApiContext.jsx';
import { sessionKey, useAssistantSession } from './useAssistantSession.js';

// useAssistantStream reaches EventSource, unavailable in jsdom; mocked here
// (same as AssistantDrawerProvider's tests) so the hook can be rendered
// standalone once a session commits.
vi.mock('./useAssistantStream.js', () => ({
  useAssistantStream: () => ({ messages: [], streaming: false, error: null, reset: vi.fn() }),
}));

// vitest, not node:test: useAssistantSession.js's import chain reaches
// api/request.js, which reads import.meta.env (a Vite-ism plain node can't
// resolve) — same reason mergeMessages.test.jsx tests one pure export of a
// .jsx file under vitest instead of node:test.
//
// Was duplicated verbatim at startSession and resetConversation call sites
// before this extraction — both must format an identical key for the same
// context, or startSession's dedupe check silently breaks.
describe('sessionKey', () => {
  it('joins provider/model/projectId/runId/source', () => {
    expect(sessionKey({ provider: 'claude', model: 'sonnet', projectId: 'p1', runId: 'r1', source: 'shared' }))
      .toBe('claude:sonnet:p1:r1:shared');
  });

  it('defaults source to "local" when absent', () => {
    expect(sessionKey({ provider: 'claude', model: 'sonnet', projectId: 'p1', runId: 'r1' }))
      .toBe('claude:sonnet:p1:r1:local');
  });

  it('two contexts differing only by source produce distinct keys', () => {
    const base = { provider: 'claude', model: 'sonnet', projectId: 'p1', runId: 'r1' };
    expect(sessionKey({ ...base, source: 'shared' })).not.toBe(sessionKey({ ...base, source: 'local' }));
  });

  it('handles a missing/undefined ctx without throwing', () => {
    expect(sessionKey(undefined)).toBe('undefined:undefined:undefined:undefined:local');
  });
});

describe('useAssistantSession via injected api (useApi seam)', () => {
  it('startSession race: the latest requested context commits, even if it resolves first', async () => {
    const deferred = {};
    const fakeApi = {
      createAssistantSession: vi.fn((ctx) => new Promise((resolve) => {
        deferred[ctx.projectId] = () => resolve({ sessionId: `sess-${ctx.projectId}` });
      })),
      fetchAssistantWorkspace: vi.fn(),
      postAssistantMessage: vi.fn().mockResolvedValue({ accepted: true }),
      stopAssistantTurn: vi.fn(),
    };
    const { result } = renderHook(() => useAssistantSession(), {
      wrapper: ({ children }) => <ApiProvider value={fakeApi}>{children}</ApiProvider>,
    });

    // Fire both startSession calls without awaiting; neither has resolved yet.
    await act(async () => {
      result.current.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pA', runId: 'r' });
      result.current.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pB', runId: 'r' });
    });
    // Resolve pB (latest) first, then pA (older) last.
    await act(async () => { deferred.pB(); await Promise.resolve(); });
    await act(async () => { deferred.pA(); await Promise.resolve(); });

    // The stale pA resolution must be ignored — pB's session stays committed.
    expect(result.current.sessionId).toBe('sess-pB');
    await act(async () => { await result.current.sendMessage('x', {}); });
    expect(fakeApi.postAssistantMessage).toHaveBeenCalledWith(
      'sess-pB', { text: 'x', uiState: {}, webEnabled: false, writeEnabled: false },
    );
  });
});
