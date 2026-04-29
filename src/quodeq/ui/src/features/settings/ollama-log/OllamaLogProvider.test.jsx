import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider } from '../../side-pane/index.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { OllamaLogProvider } from './OllamaLogProvider.jsx';
import { useOllamaLog } from './OllamaLogContext.js';

// Mock EventSource so useOllamaLogStream doesn't throw.
class MockEventSource {
  static instances = [];
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.readyState = 0;
    this.closed = false;
    MockEventSource.instances.push(this);
  }
  addEventListener() {}
  removeEventListener() {}
  set onmessage(_fn) {}
  set onerror(_fn) {}
  close() { this.closed = true; this.readyState = 2; }
}

function Probe() {
  const { open, openLog, closeLog } = useOllamaLog();
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
      <OllamaLogProvider>{ui}</OllamaLogProvider>
    </SidePaneProvider>
  );
}

describe('OllamaLogProvider', () => {
  let originalEventSource;
  beforeEach(() => {
    originalEventSource = globalThis.EventSource;
    globalThis.EventSource = MockEventSource;
    MockEventSource.instances = [];
  });
  afterEach(() => {
    globalThis.EventSource = originalEventSource;
    vi.restoreAllMocks();
  });

  it('initial state: closed, dock empty', () => {
    renderWithProviders(<Probe />);
    expect(screen.getByTestId('open')).toHaveTextContent('no');
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
  });

  it('openLog adds the ollama-log window', () => {
    renderWithProviders(<Probe />);
    fireEvent.click(screen.getByText('open'));
    expect(screen.getByTestId('open')).toHaveTextContent('yes');
    expect(screen.getByTestId('dock')).toHaveTextContent('ollama-log');
  });

  it('closeLog removes window and flips state to closed', () => {
    renderWithProviders(<Probe />);
    fireEvent.click(screen.getByText('open'));
    fireEvent.click(screen.getByText('close'));
    expect(screen.getByTestId('open')).toHaveTextContent('no');
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
  });
});
