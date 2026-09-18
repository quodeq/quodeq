import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const drawer = {
  closeActiveTab: vi.fn(), maximized: false, toggleMaximized: vi.fn(),
  provider: 'ollama', model: 'm', openPanels: ['assistant'], streaming: true,
  webEnabled: false, toggleWebEnabled: vi.fn(),
  writeEnabled: false, toggleWriteEnabled: vi.fn(),
  repoInfo: null, workspace: null, refreshWorkspace: vi.fn(),
  sessionId: 's1', sessionReady: true, resetConversation: vi.fn(), readOnly: false,
};
vi.mock('./AssistantDrawerProvider.jsx', () => ({ useAssistantDrawer: () => drawer }));
vi.mock('../side-pane/index.js', () => ({
  useSidePane: () => ({ addWindow: vi.fn() }),
  workspaceDiffSpec: vi.fn(),
}));

import AssistantHeader from './AssistantHeader.jsx';

describe('AssistantHeader streaming indicator accessibility', () => {
  it('announces "Assistant is responding" while streaming, alongside the aria-hidden compass', () => {
    render(<AssistantHeader />);
    expect(screen.getByRole('status')).toHaveTextContent('Assistant is responding');
  });

  it('renders no status region when not streaming', () => {
    drawer.streaming = false;
    render(<AssistantHeader />);
    expect(screen.queryByRole('status')).toBeNull();
    drawer.streaming = true;
  });
});
