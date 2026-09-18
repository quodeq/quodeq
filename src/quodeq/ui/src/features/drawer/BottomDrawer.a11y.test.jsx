import { it, expect, vi, describe } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const drawer = {
  isOpen: true, height: 320, setHeight: vi.fn(), close: vi.fn(), closeActiveTab: vi.fn(),
  openPanels: ['assistant'], activeTab: 'assistant', selectTab: vi.fn(),
  maximized: false, toggleMaximized: vi.fn(), setMaximized: vi.fn(),
  provider: 'ollama', model: 'm', messages: [], streaming: false, error: null, sendMessage: vi.fn(),
  webEnabled: false, toggleWebEnabled: vi.fn(),
  sessionReady: true, resetConversation: vi.fn(),
  repoInfo: null, readOnly: false,
};
vi.mock('../assistant/AssistantDrawerProvider.jsx', () => ({ useAssistantDrawer: () => drawer }));
vi.mock('../terminal/TerminalPane.jsx', () => ({ default: () => <div data-testid="tty" /> }));
vi.mock('../side-pane/index.js', () => ({
  useSidePane: () => ({ addWindow: vi.fn() }),
  workspaceDiffSpec: vi.fn(),
}));
import { BottomDrawer } from './BottomDrawer.jsx';

describe('BottomDrawer resize handle keyboard accessibility', () => {
  it('is focusable via tabIndex=0', () => {
    render(<BottomDrawer uiState={{}} />);
    const handle = screen.getByRole('separator', { name: /resize drawer/i });
    expect(handle).toHaveAttribute('tabindex', '0');
  });

  it('ArrowUp grows the drawer height by RESIZE_STEP_PX (16)', () => {
    drawer.setHeight.mockClear();
    render(<BottomDrawer uiState={{}} />);
    const handle = screen.getByRole('separator', { name: /resize drawer/i });
    fireEvent.keyDown(handle, { key: 'ArrowUp' });
    expect(drawer.setHeight).toHaveBeenCalledWith(336);
  });

  it('ArrowDown shrinks the drawer height by RESIZE_STEP_PX (16)', () => {
    drawer.setHeight.mockClear();
    render(<BottomDrawer uiState={{}} />);
    const handle = screen.getByRole('separator', { name: /resize drawer/i });
    fireEvent.keyDown(handle, { key: 'ArrowDown' });
    expect(drawer.setHeight).toHaveBeenCalledWith(304);
  });
});
