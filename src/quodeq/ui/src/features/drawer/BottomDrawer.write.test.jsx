import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// Stable addWindow so a chip-click test can assert on the call. `vi.hoisted`
// makes it exist before the hoisted vi.mock factory below runs.
const { mockAddWindow } = vi.hoisted(() => ({ mockAddWindow: vi.fn() }));

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
  useSidePane: () => ({ addWindow: mockAddWindow }),
  workspaceDiffSpec: vi.fn((a) => ({ id: `workspace-diff:${a.sessionId}:${a.key}` })),
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

  it('opens a per-worktree diff window keyed by createdAt', () => {
    mockAddWindow.mockClear();
    drawerState.repoInfo = { attached: true, reason: 'ok', writeAvailable: true };
    drawerState.workspace = { branch: 'quodeq/fix-x', status: 'active', filesChanged: 2, createdAt: '2026-07-10 10:00:00' };
    render(<BottomDrawer uiState={{}} />);
    fireEvent.click(screen.getByText('2 files changed'));
    expect(mockAddWindow).toHaveBeenCalledWith(
      expect.objectContaining({ id: expect.stringContaining('2026-07-10 10:00:00') }));

    // A NEW worktree (different createdAt) yields a DISTINCT window id, so the
    // stale post-apply panel is not deduped over.
    mockAddWindow.mockClear();
    drawerState.workspace = { branch: 'quodeq/fix-x', status: 'active', filesChanged: 1, createdAt: '2026-07-10 11:30:00' };
    render(<BottomDrawer uiState={{}} />);
    fireEvent.click(screen.getByText('1 file changed'));
    expect(mockAddWindow).toHaveBeenCalledWith(
      expect.objectContaining({ id: expect.stringContaining('2026-07-10 11:30:00') }));
    expect(mockAddWindow).not.toHaveBeenCalledWith(
      expect.objectContaining({ id: expect.stringContaining('2026-07-10 10:00:00') }));
  });
});
