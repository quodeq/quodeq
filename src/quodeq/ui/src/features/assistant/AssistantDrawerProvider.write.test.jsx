import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';

// Hoisted holder so the useAssistantStream mock can hand the provider's
// onDone callback back to the test (vi.mock is hoisted above imports).
const streamHooks = vi.hoisted(() => ({ onDone: null }));

vi.mock('../../api/assistant.js', () => ({
  createAssistantSession: vi.fn().mockResolvedValue({
    sessionId: 's1', repoAttached: true, repoReason: 'ok', writeAvailable: true,
  }),
  postAssistantMessage: vi.fn().mockResolvedValue({ accepted: true }),
  fetchAssistantCatalog: vi.fn().mockResolvedValue({ commands: [], skills: [], actions: [] }),
  fetchAssistantWorkspace: vi.fn().mockResolvedValue({ worktree: null, pending: [] }),
}));
vi.mock('../settings/hooks/useAssistantProvider.js', () => ({
  default: () => ({ enabled: true }),
}));
vi.mock('../settings/hooks/useTerminalSettings.js', () => ({
  default: () => ({ enabled: false }),
}));
vi.mock('./useAssistantStream.js', () => ({
  useAssistantStream: (_sessionId, opts) => {
    streamHooks.onDone = opts?.onDone || null;  // capture so tests can fire it
    return { messages: [], error: null };
  },
}));

import { createAssistantSession, fetchAssistantWorkspace, postAssistantMessage } from '../../api/assistant.js';
import { AssistantDrawerProvider, useAssistantDrawer } from './AssistantDrawerProvider.jsx';

let drawer;
function Probe() {
  drawer = useAssistantDrawer();
  return null;
}

function mount() {
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
}

describe('write grant state', () => {
  beforeEach(() => { drawer = null; streamHooks.onDone = null; });

  it('captures repoInfo from session create and sends writeEnabled', async () => {
    mount();
    await act(() => drawer.startSession({ provider: 'ollama', model: 'm', projectId: 'p' }));
    expect(drawer.repoInfo).toEqual({ attached: true, reason: 'ok', writeAvailable: true });
    act(() => drawer.toggleWriteEnabled());
    expect(drawer.writeEnabled).toBe(true);
    await act(() => drawer.sendMessage('fix it', { view: 'x' }));
    expect(postAssistantMessage).toHaveBeenCalledWith('s1',
      expect.objectContaining({ writeEnabled: true }));
  });

  it('resets writeEnabled on a new conversation', async () => {
    mount();
    await act(() => drawer.startSession({ provider: 'ollama', model: 'm', projectId: 'p' }));
    act(() => drawer.toggleWriteEnabled());
    await act(() => drawer.resetConversation());
    expect(drawer.writeEnabled).toBe(false);
  });

  it('ignores a workspace refresh that resolves after a context switch', async () => {
    // Distinct session ids per context so the stale-guard has something to
    // compare (A's late fetch must not overwrite B's freshly-cleared state).
    createAssistantSession.mockImplementation((ctx) => Promise.resolve({
      sessionId: `sess-${ctx.projectId}`,
      repoAttached: true, repoReason: 'ok', writeAvailable: true,
    }));
    // Session A's workspace fetch resolves on a deferred we control.
    let resolveWs;
    const deferred = new Promise((res) => { resolveWs = res; });
    fetchAssistantWorkspace.mockReturnValueOnce(deferred);

    mount();
    await act(() => drawer.startSession({ provider: 'ollama', model: 'm', projectId: 'A' }));
    act(() => drawer.toggleWriteEnabled());

    // Fire onDone for session A (write-enabled) -> refreshWorkspace starts and
    // awaits the deferred fetch.
    act(() => { streamHooks.onDone(); });

    // Switch to a different context BEFORE A's workspace fetch resolves; this
    // clears workspace to null and points sessionIdRef at B.
    await act(() => drawer.startSession({ provider: 'ollama', model: 'm', projectId: 'B' }));
    expect(drawer.workspace).toBeNull();

    // Now resolve session A's late workspace; it must NOT overwrite B's null.
    await act(async () => {
      resolveWs({ worktree: { branch: 'quodeq/fix-a', status: 'active', filesChanged: 3 } });
      await deferred;
      await Promise.resolve();
    });
    expect(drawer.workspace).toBeNull();
  });
});
