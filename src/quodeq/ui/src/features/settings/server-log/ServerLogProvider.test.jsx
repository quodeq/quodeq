import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider } from '../../side-pane/index.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { ServerLogProvider } from './ServerLogProvider.jsx';
import { useServerLog } from './ServerLogContext.js';

function Probe() {
  const { open, openLog, closeLog } = useServerLog();
  const { windows } = useSidePane();
  return (
    <div>
      <div data-testid="open">{open ? 'yes' : 'no'}</div>
      <div data-testid="dock">{windows.map((w) => w.id).join(',') || 'empty'}</div>
      <button onClick={openLog}>open</button>
      <button onClick={closeLog}>close</button>
    </div>
  );
}

function renderWithProviders(ui) {
  return render(
    <SidePaneProvider>
      <ServerLogProvider>{ui}</ServerLogProvider>
    </SidePaneProvider>
  );
}

describe('ServerLogProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ lines: [] }) });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('initial state: closed, dock empty', () => {
    renderWithProviders(<Probe />);
    expect(screen.getByTestId('open')).toHaveTextContent('no');
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
  });

  it('openLog adds the server-log window', async () => {
    renderWithProviders(<Probe />);
    fireEvent.click(screen.getByText('open'));
    expect(screen.getByTestId('open')).toHaveTextContent('yes');
    expect(screen.getByTestId('dock')).toHaveTextContent('server-log');
  });

  it('closeLog removes the window and flips state to closed', async () => {
    renderWithProviders(<Probe />);
    fireEvent.click(screen.getByText('open'));
    fireEvent.click(screen.getByText('close'));
    expect(screen.getByTestId('open')).toHaveTextContent('no');
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
  });
});
