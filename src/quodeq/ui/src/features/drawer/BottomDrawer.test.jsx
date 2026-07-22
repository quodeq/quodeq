import { it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const drawer = {
  isOpen: true, height: 320, setHeight: vi.fn(), close: vi.fn(), closeActiveTab: vi.fn(),
  openPanels: ['assistant', 'terminal'], activeTab: 'assistant', selectTab: vi.fn(),
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

it('the hide button hides only the active tab, not the whole drawer', () => {
  render(<BottomDrawer uiState={{}} />);
  fireEvent.click(screen.getByRole('button', { name: /hide tab/i }));
  expect(drawer.closeActiveTab).toHaveBeenCalled();
  expect(drawer.close).not.toHaveBeenCalled();
});

it('the maximized-restore glyph is distinct from the hide chevron', () => {
  // Both panels hide (nothing is killed), so the hide button is a chevron-down.
  // When maximized, the restore control must NOT render the same chevron-down
  // next to it — it uses the shrink glyph instead.
  drawer.maximized = true;
  render(<BottomDrawer uiState={{}} />);
  const restore = screen.getByRole('button', { name: /restore/i });
  const hide = screen.getByRole('button', { name: /hide tab/i });
  expect(restore.innerHTML).not.toBe(hide.innerHTML);
  drawer.maximized = false;
});

it('the model chip sits with the tabs on the left, not in the right controls', () => {
  render(<BottomDrawer uiState={{}} />);
  const chip = screen.getByTitle('Ollama · m');
  expect(chip.closest('.assistant-drawer-controls')).toBeNull();
  expect(chip.previousElementSibling).toHaveClass('drawer-tabs');
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

it('the new-conversation control resets the conversation', () => {
  render(<BottomDrawer uiState={{}} />);
  fireEvent.click(screen.getByRole('button', { name: /new conversation/i }));
  expect(drawer.resetConversation).toHaveBeenCalled();
});

it('disables the new-conversation control while streaming and before a session exists', () => {
  drawer.streaming = true;
  const { unmount } = render(<BottomDrawer uiState={{}} />);
  expect(screen.getByRole('button', { name: /new conversation/i })).toBeDisabled();
  drawer.streaming = false;
  unmount();
  drawer.sessionReady = false;
  render(<BottomDrawer uiState={{}} />);
  expect(screen.getByRole('button', { name: /new conversation/i })).toBeDisabled();
  drawer.sessionReady = true;
});

it('hides the new-conversation control while the terminal tab is active', () => {
  drawer.activeTab = 'terminal';
  render(<BottomDrawer uiState={{}} />);
  expect(screen.queryByRole('button', { name: /new conversation/i })).toBeNull();
  drawer.activeTab = 'assistant';
});

it('shows NO repo chip when the repo is attached (exception-only signal)', () => {
  drawer.repoInfo = { attached: true, reason: null, writeAvailable: false };
  render(<BottomDrawer uiState={{}} />);
  expect(screen.queryByText('repo')).toBeNull();
  expect(screen.queryByText(/no repo/)).toBeNull();
  drawer.repoInfo = null;
});

it('warns with "no repo access" and the server reason when not attached', () => {
  drawer.repoInfo = { attached: false, reason: 'online_project', writeAvailable: false };
  render(<BottomDrawer uiState={{}} />);
  const chip = screen.getByText('no repo access');
  expect(chip).toHaveClass('badge', 'badge--tag', 'badge--warning');
  expect(chip).toHaveAttribute('title', 'Repository not attached: online_project');
  drawer.repoInfo = null;
});

it('the model chip is an accent Badge', () => {
  render(<BottomDrawer uiState={{}} />);
  expect(screen.getByTitle('Ollama · m')).toHaveClass('badge', 'badge--tag', 'badge--accent', 'drawer-model-chip');
});

it('shows a read-only info badge when the session is read-only', () => {
  drawer.readOnly = true;
  render(<BottomDrawer uiState={{}} />);
  const chip = screen.getByText('read-only');
  expect(chip).toHaveClass('badge', 'badge--tag', 'badge--info');
  expect(chip).toHaveAttribute('title', 'Remote project session: read tools only');
  drawer.readOnly = false;
});

it('shows NO read-only badge for normal sessions', () => {
  render(<BottomDrawer uiState={{}} />);
  expect(screen.queryByText('read-only')).toBeNull();
});
