import { it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const drawer = {
  isOpen: true, height: 320, setHeight: vi.fn(), close: vi.fn(), closeActiveTab: vi.fn(),
  openPanels: ['assistant', 'terminal'], activeTab: 'assistant', selectTab: vi.fn(),
  maximized: false, toggleMaximized: vi.fn(), setMaximized: vi.fn(),
  provider: 'ollama', model: 'm', messages: [], streaming: false, error: null, sendMessage: vi.fn(),
  webEnabled: false, toggleWebEnabled: vi.fn(),
};
vi.mock('../assistant/AssistantDrawerProvider.jsx', () => ({ useAssistantDrawer: () => drawer }));
vi.mock('../terminal/TerminalPane.jsx', () => ({ default: () => <div data-testid="tty" /> }));
import { BottomDrawer } from './BottomDrawer.jsx';

it('shows a tab for each OPEN panel (both, since both are open)', () => {
  render(<BottomDrawer uiState={{}} />);
  expect(screen.getByRole('tab', { name: /Assistant/ })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: /Terminal/ })).toBeInTheDocument();
});

it('only shows a tab for the single open panel when only one is open', () => {
  drawer.openPanels = ['assistant'];
  render(<BottomDrawer uiState={{}} />);
  expect(screen.getByRole('tab', { name: /Assistant/ })).toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: /Terminal/ })).toBeNull();
  drawer.openPanels = ['assistant', 'terminal'];  // restore for other tests
});

it('clicking an inactive tab activates it (without deselecting the other)', () => {
  render(<BottomDrawer uiState={{}} />);
  fireEvent.click(screen.getByRole('tab', { name: /Terminal/ }));
  expect(drawer.selectTab).toHaveBeenCalledWith('terminal');
});

it('keeps the terminal panel mounted but hidden while the assistant tab is active', async () => {
  render(<BottomDrawer uiState={{}} />);
  const tty = await screen.findByTestId('tty');
  expect(tty.closest('.drawer-panel')).toHaveStyle({ display: 'none' });
});

it('the maximize control toggles the maximized state', () => {
  render(<BottomDrawer uiState={{}} />);
  fireEvent.click(screen.getByRole('button', { name: /maximize/i }));
  expect(drawer.toggleMaximized).toHaveBeenCalled();
});

it('the close (×) button closes only the active tab, not the whole drawer', () => {
  render(<BottomDrawer uiState={{}} />);
  fireEvent.click(screen.getByRole('button', { name: /close tab/i }));
  expect(drawer.closeActiveTab).toHaveBeenCalled();
  expect(drawer.close).not.toHaveBeenCalled();
});

it('shows the web toggle for web-capable providers and toggles it', () => {
  render(<BottomDrawer uiState={{}} />);
  const globe = screen.getByRole('button', { name: /web access/i });
  expect(globe).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(globe);
  expect(drawer.toggleWebEnabled).toHaveBeenCalled();
});

it('hides the web toggle for providers without web support', () => {
  drawer.provider = 'gemini';
  render(<BottomDrawer uiState={{}} />);
  expect(screen.queryByRole('button', { name: /web access/i })).toBeNull();
  drawer.provider = 'ollama';
});

it('hides the web toggle while the terminal tab is active', () => {
  drawer.activeTab = 'terminal';
  render(<BottomDrawer uiState={{}} />);
  expect(screen.queryByRole('button', { name: /web access/i })).toBeNull();
  drawer.activeTab = 'assistant';
});

it('disables the web toggle while a turn is streaming', () => {
  drawer.streaming = true;
  render(<BottomDrawer uiState={{}} />);
  expect(screen.getByRole('button', { name: /web access/i })).toBeDisabled();
  drawer.streaming = false;
});
