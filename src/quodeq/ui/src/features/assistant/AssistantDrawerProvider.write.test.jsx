import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';

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
  useAssistantStream: () => ({ messages: [], error: null }),
}));

import { postAssistantMessage } from '../../api/assistant.js';
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
  beforeEach(() => { drawer = null; });

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
});
