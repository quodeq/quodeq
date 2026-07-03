import { it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const killTerminal = vi.fn(() => Promise.resolve({ ok: true }));
vi.mock('../../../api/terminal.js', () => ({ killTerminal: (...a) => killTerminal(...a) }));
import TerminalSection from './TerminalSection.jsx';

beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); });

it('toggles the terminal on and off', () => {
  render(<TerminalSection />);
  fireEvent.click(screen.getByRole('tab', { name: 'On' }));
  expect(localStorage.getItem('cc-terminal-enabled')).toBe('true');
});

it('Restart terminal kills the server session and signals the pane to reconnect', async () => {
  localStorage.setItem('cc-terminal-enabled', 'true');
  const onRestart = vi.fn();
  window.addEventListener('quodeq:terminal-restart', onRestart);
  render(<TerminalSection />);
  fireEvent.click(screen.getByRole('button', { name: /restart terminal/i }));
  expect(killTerminal).toHaveBeenCalled();
  await waitFor(() => expect(onRestart).toHaveBeenCalled());  // dispatched after kill resolves
  window.removeEventListener('quodeq:terminal-restart', onRestart);
});

it('does not signal a reconnect when the kill fails (avoids restarting onto the same live shell)', async () => {
  localStorage.setItem('cc-terminal-enabled', 'true');
  killTerminal.mockRejectedValueOnce(new Error('boom'));
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  const onRestart = vi.fn();
  window.addEventListener('quodeq:terminal-restart', onRestart);
  render(<TerminalSection />);
  fireEvent.click(screen.getByRole('button', { name: /restart terminal/i }));
  await waitFor(() => expect(warn).toHaveBeenCalled());
  expect(onRestart).not.toHaveBeenCalled();
  window.removeEventListener('quodeq:terminal-restart', onRestart);
  warn.mockRestore();
});
