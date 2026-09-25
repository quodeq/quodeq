import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useTerminalRestart } from './useTerminalRestart.js';

vi.mock('../../../utils/confirmDialog.js', () => ({ confirmDialog: vi.fn() }));
import { confirmDialog } from '../../../utils/confirmDialog.js';

function wrapper(api) {
  return function Wrapper({ children }) {
    return <ApiProvider value={api}>{children}</ApiProvider>;
  };
}

describe('useTerminalRestart', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('kills the terminal (via useApi()) after confirmation, then signals the pane to reconnect', async () => {
    confirmDialog.mockResolvedValue(true);
    const killTerminal = vi.fn().mockResolvedValue({ ok: true });
    const onRestart = vi.fn();
    window.addEventListener('quodeq:terminal-restart', onRestart);
    const { result } = renderHook(() => useTerminalRestart(), { wrapper: wrapper({ killTerminal }) });

    await act(async () => { await result.current(); });

    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({ variant: 'danger' }));
    expect(killTerminal).toHaveBeenCalled();
    await waitFor(() => expect(onRestart).toHaveBeenCalled());
    window.removeEventListener('quodeq:terminal-restart', onRestart);
  });

  it('does not call killTerminal when the confirm dialog is cancelled', async () => {
    confirmDialog.mockResolvedValue(false);
    const killTerminal = vi.fn().mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useTerminalRestart(), { wrapper: wrapper({ killTerminal }) });

    await act(async () => { await result.current(); });

    expect(killTerminal).not.toHaveBeenCalled();
  });

  it('does not signal a reconnect when the kill fails', async () => {
    confirmDialog.mockResolvedValue(true);
    const killTerminal = vi.fn().mockRejectedValue(new Error('boom'));
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const onRestart = vi.fn();
    window.addEventListener('quodeq:terminal-restart', onRestart);
    const { result } = renderHook(() => useTerminalRestart(), { wrapper: wrapper({ killTerminal }) });

    await act(async () => { await result.current(); });

    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(onRestart).not.toHaveBeenCalled();
    window.removeEventListener('quodeq:terminal-restart', onRestart);
    warn.mockRestore();
  });
});
