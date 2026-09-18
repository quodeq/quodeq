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

  it('ignores a key name that only exists on Object.prototype', () => {
    // Guard, not a regression test: React's own getEventKey does
    // `normalizeKey[nativeEvent.key] || nativeEvent.key` first, so these names
    // already arrive as a function or object and miss the direction map
    // whichever way it is read. The hasOwn check is what makes that
    // independent of React's accident.
    drawer.setHeight.mockClear();
    render(<BottomDrawer uiState={{}} />);
    const handle = screen.getByRole('separator', { name: /resize drawer/i });
    fireEvent.keyDown(handle, { key: 'constructor' });
    fireEvent.keyDown(handle, { key: 'toString' });
    expect(drawer.setHeight).not.toHaveBeenCalled();
  });

  it('resizing a maximized drawer with the keyboard leaves maximized and starts from the rendered height', () => {
    drawer.setHeight.mockClear();
    drawer.setMaximized.mockClear();
    drawer.maximized = true;
    try {
      render(<BottomDrawer uiState={{}} />);
      const handle = screen.getByRole('separator', { name: /resize drawer/i });
      vi.spyOn(handle.parentElement, 'getBoundingClientRect').mockReturnValue({ height: 500 });
      fireEvent.keyDown(handle, { key: 'ArrowDown' });
      expect(drawer.setMaximized).toHaveBeenCalledWith(false);
      expect(drawer.setHeight).toHaveBeenCalledWith(484);
    } finally {
      drawer.maximized = false;
    }
  });
});
