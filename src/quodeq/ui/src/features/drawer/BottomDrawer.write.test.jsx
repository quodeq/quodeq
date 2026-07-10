import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const drawerState = {
  isOpen: true, height: 320, setHeight: vi.fn(), closeActiveTab: vi.fn(),
  openPanels: ['assistant'], activeTab: 'assistant', selectTab: vi.fn(),
  maximized: false, toggleMaximized: vi.fn(), setMaximized: vi.fn(),
  provider: 'ollama', model: 'm', streaming: false,
  webEnabled: false, toggleWebEnabled: vi.fn(),
  sessionReady: true, resetConversation: vi.fn(),
  writeEnabled: false, toggleWriteEnabled: vi.fn(),
  repoInfo: { attached: true, reason: 'ok', writeAvailable: true },
  workspace: { branch: 'quodeq/fix-x', status: 'active', filesChanged: 3, stats: [] },
  refreshWorkspace: vi.fn(), sessionId: 's1',
};

vi.mock('../assistant/AssistantDrawerProvider.jsx', () => ({
  useAssistantDrawer: () => drawerState,
}));
vi.mock('../assistant/AssistantDrawer.jsx', () => ({
  AssistantPane: () => <div data-testid="pane" />,
}));
vi.mock('../side-pane/index.js', () => ({
  useSidePane: () => ({ addWindow: vi.fn() }),
}));

import { BottomDrawer } from './BottomDrawer.jsx';

describe('drawer write affordances', () => {
  it('renders write toggle, repo chip and pending-changes chip', () => {
    render(<BottomDrawer uiState={{}} />);
    expect(screen.getByLabelText('Allow repository edits for this conversation')).toBeTruthy();
    expect(screen.getByTitle('Repository attached')).toBeTruthy();
    expect(screen.getByText('3 files changed')).toBeTruthy();
  });

  it('hides the write toggle when writeAvailable is false', () => {
    drawerState.repoInfo = { attached: false, reason: 'path_missing', writeAvailable: false };
    drawerState.workspace = null;
    render(<BottomDrawer uiState={{}} />);
    expect(screen.queryByLabelText('Allow repository edits for this conversation')).toBeNull();
    expect(screen.getByTitle(/Repository not attached/)).toBeTruthy();
  });
});
