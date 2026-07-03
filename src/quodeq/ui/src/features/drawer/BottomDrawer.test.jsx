import { it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const drawer = { isOpen: true, height: 320, setHeight: vi.fn(), close: vi.fn(),
  activeTab: 'assistant', openTab: vi.fn(),
  maximized: false, toggleMaximized: vi.fn(), setMaximized: vi.fn(),
  provider: 'ollama', model: 'm', messages: [], streaming: false, error: null, sendMessage: vi.fn() };
vi.mock('../assistant/AssistantDrawerProvider.jsx', () => ({ useAssistantDrawer: () => drawer }));
vi.mock('../settings/hooks/useAssistantProvider.js', () => ({ default: () => ({ enabled: true }) }));
vi.mock('../settings/hooks/useTerminalSettings.js', () => ({ default: () => ({ enabled: true }) }));
vi.mock('../terminal/TerminalPane.jsx', () => ({ default: () => <div data-testid="tty" /> }));
import { BottomDrawer } from './BottomDrawer.jsx';

it('shows only the active (assistant) tab label, not a strip of both tabs', () => {
  render(<BottomDrawer uiState={{}} />);
  expect(screen.getByText('✦ Assistant')).toBeInTheDocument();
  // No dual-tab strip: the terminal tab is not offered in the drawer header
  // (switching is via the topbar launcher).
  expect(screen.queryByText('❯_ Terminal')).toBeNull();
});

it('keeps the terminal panel mounted but hidden while the assistant tab is active', async () => {
  render(<BottomDrawer uiState={{}} />);
  // findBy* waits for the lazy TerminalPane to resolve through Suspense.
  const tty = await screen.findByTestId('tty');
  expect(tty).toBeInTheDocument();
  // Its panel is present but hidden (display:none), not unmounted.
  expect(tty.closest('.drawer-panel')).toHaveStyle({ display: 'none' });
});

it('the maximize control toggles the maximized state', () => {
  render(<BottomDrawer uiState={{}} />);
  fireEvent.click(screen.getByRole('button', { name: /maximize/i }));
  expect(drawer.toggleMaximized).toHaveBeenCalled();
});
