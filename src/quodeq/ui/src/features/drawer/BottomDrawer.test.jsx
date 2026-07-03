import { it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const drawer = { isOpen: true, height: 320, setHeight: vi.fn(), close: vi.fn(),
  activeTab: 'assistant', openTab: vi.fn(),
  provider: 'ollama', model: 'm', messages: [], streaming: false, error: null, sendMessage: vi.fn() };
vi.mock('../assistant/AssistantDrawerProvider.jsx', () => ({ useAssistantDrawer: () => drawer }));
vi.mock('../settings/hooks/useAssistantProvider.js', () => ({ default: () => ({ enabled: true }) }));
vi.mock('../settings/hooks/useTerminalSettings.js', () => ({ default: () => ({ enabled: true }) }));
vi.mock('../terminal/TerminalPane.jsx', () => ({ default: () => <div data-testid="tty" /> }));
import { BottomDrawer } from './BottomDrawer.jsx';

it('shows both tabs and keeps the terminal panel mounted but hidden when assistant is active', async () => {
  render(<BottomDrawer uiState={{}} />);
  expect(screen.getByRole('tab', { name: /Assistant/ })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: /Terminal/ })).toBeInTheDocument();
  // Terminal pane stays in the DOM (mounted) even while assistant tab is active.
  // findBy* waits for the lazy TerminalPane to resolve through Suspense.
  const tty = await screen.findByTestId('tty');
  expect(tty).toBeInTheDocument();
  // Its panel is present but hidden (display:none), not unmounted.
  expect(tty.closest('.drawer-panel')).toHaveStyle({ display: 'none' });
});
