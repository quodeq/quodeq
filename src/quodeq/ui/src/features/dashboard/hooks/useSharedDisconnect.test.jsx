import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useSharedDisconnect } from './useSharedDisconnect.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

vi.mock('../../../utils/confirmDialog.js', () => ({ confirmDialog: vi.fn(async () => true) }));
const showToast = vi.fn();
vi.mock('../../side-pane/SidePaneContext.jsx', () => ({ useSidePane: () => ({ showToast }) }));

// A disconnect can take a while (the server waits for the shared warm-up's
// project in flight), so the strip shows it busy and a second click cannot
// start a second disconnect.
function wrap(fakeApi, children) {
  const QC = withQueryClient();
  return (
    <QC>
      <ApiProvider value={fakeApi}>{children}</ApiProvider>
    </QC>
  );
}

describe('useSharedDisconnect', () => {
  it('reports disconnecting while the request is in flight, and once only', async () => {
    let finish;
    const fakeApi = { disconnectShared: vi.fn(() => new Promise((resolve) => { finish = resolve; })) };
    const onDisconnected = vi.fn();
    const { result } = renderHook(
      () => useSharedDisconnect({ onDisconnected }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    expect(result.current.disconnecting).toBe(false);

    act(() => { result.current.disconnect(); });
    await waitFor(() => expect(result.current.disconnecting).toBe(true));
    await act(async () => { await result.current.disconnect(); });
    expect(fakeApi.disconnectShared).toHaveBeenCalledTimes(1);

    await act(async () => { finish({ configured: false }); });
    await waitFor(() => expect(result.current.disconnecting).toBe(false));
    expect(onDisconnected).toHaveBeenCalledTimes(1);
  });

  it('clears disconnecting after a failure and says so', async () => {
    const fakeApi = { disconnectShared: vi.fn(async () => { throw new Error('boom'); }) };
    const { result } = renderHook(() => useSharedDisconnect(), { wrapper: ({ children }) => wrap(fakeApi, children) });
    await act(async () => { await result.current.disconnect(); });
    expect(result.current.disconnecting).toBe(false);
    expect(showToast).toHaveBeenCalled();
  });
});
