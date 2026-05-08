import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider } from '../../side-pane/index.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { EvalLogProvider } from './EvalLogProvider.jsx';
import { useEvalLog } from './EvalLogContext.js';

class MockEventSource {
  static instances = [];
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.readyState = 0;
    this.closed = false;
    MockEventSource.instances.push(this);
  }
  addEventListener(name, fn) { (this.listeners[name] = this.listeners[name] || []).push(fn); }
  removeEventListener(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter((f) => f !== fn); }
  set onmessage(fn) { this._onmessage = fn; }
  get onmessage() { return this._onmessage; }
  set onerror(fn) { this._onerror = fn; }
  get onerror() { return this._onerror; }
  emit(name, event) {
    if (name === 'message' && this._onmessage) this._onmessage(event);
    (this.listeners[name] || []).forEach((fn) => fn(event));
  }
  close() { this.closed = true; }
}

function Probe() {
  const { activeJobId, openLog, closeLog } = useEvalLog();
  const { windows } = useSidePane();
  return (
    <div>
      <div data-testid="active">{activeJobId || 'none'}</div>
      <div data-testid="dock">{windows.map((w) => w.id).join(',') || 'empty'}</div>
      <button onClick={() => openLog('job-a', 'Run A')}>open-a</button>
      <button onClick={() => openLog('job-b', 'Run B')}>open-b</button>
      <button onClick={closeLog}>close</button>
    </div>
  );
}

function renderWithProviders(ui) {
  return render(
    <SidePaneProvider>
      <EvalLogProvider>
        {ui}
      </EvalLogProvider>
    </SidePaneProvider>
  );
}

describe('EvalLogProvider', () => {
  let originalEventSource;
  beforeEach(() => {
    originalEventSource = globalThis.EventSource;
    globalThis.EventSource = MockEventSource;
    MockEventSource.instances = [];
  });
  afterEach(() => { globalThis.EventSource = originalEventSource; });

  it('initial state: no active job, dock empty', () => {
    renderWithProviders(<Probe />);
    expect(screen.getByTestId('active')).toHaveTextContent('none');
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
  });

  it('openLog adds the eval-log window and sets activeJobId', () => {
    renderWithProviders(<Probe />);
    fireEvent.click(screen.getByText('open-a'));
    expect(screen.getByTestId('active')).toHaveTextContent('job-a');
    expect(screen.getByTestId('dock')).toHaveTextContent('eval-log');
  });

  it('closeLog removes the window and clears activeJobId', () => {
    renderWithProviders(<Probe />);
    fireEvent.click(screen.getByText('open-a'));
    fireEvent.click(screen.getByText('close'));
    expect(screen.getByTestId('active')).toHaveTextContent('none');
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
  });

  it('openLog with a different jobId while open swaps content without re-toggling the slot', () => {
    renderWithProviders(<Probe />);
    fireEvent.click(screen.getByText('open-a'));
    expect(screen.getByTestId('active')).toHaveTextContent('job-a');
    fireEvent.click(screen.getByText('open-b'));
    expect(screen.getByTestId('active')).toHaveTextContent('job-b');
    expect(screen.getByTestId('dock')).toHaveTextContent('eval-log');
  });

  it('opens a new EventSource for the new jobId on swap', () => {
    renderWithProviders(<Probe />);
    fireEvent.click(screen.getByText('open-a'));
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('/api/jobs/job-a/logs/stream');
    fireEvent.click(screen.getByText('open-b'));
    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[0].closed).toBe(true);
    expect(MockEventSource.instances[1].url).toBe('/api/jobs/job-b/logs/stream');
  });

  it('updates the side-pane window body as new log lines arrive', () => {
    function ProbeWithRender() {
      const { openLog } = useEvalLog();
      const { windows } = useSidePane();
      const body = windows[0]?.render?.() ?? null;
      return (
        <div>
          <button onClick={() => openLog('job-x', 'Run X')}>open</button>
          <div data-testid="body">{body}</div>
        </div>
      );
    }
    render(
      <SidePaneProvider>
        <EvalLogProvider>
          <ProbeWithRender />
        </EvalLogProvider>
      </SidePaneProvider>
    );
    fireEvent.click(screen.getByText('open'));
    expect(screen.getByTestId('body')).toHaveTextContent('Waiting for output');
    const es = MockEventSource.instances[0];
    act(() => { es.emit('message', { data: 'hello world' }); });
    expect(screen.getByTestId('body')).toHaveTextContent('hello world');
  });

  it('clears activeJobId when the side-pane window is removed externally', () => {
    function SyncProbe() {
      const { activeJobId, openLog } = useEvalLog();
      const { windows, removeWindow, closeAll } = useSidePane();
      return (
        <div>
          <div data-testid="active">{activeJobId || 'none'}</div>
          <div data-testid="dock">{windows.map((w) => w.id).join(',') || 'empty'}</div>
          <button onClick={() => openLog('job-a', 'Run A')}>open</button>
          <button onClick={() => removeWindow('eval-log')}>remove-via-x</button>
          <button onClick={closeAll}>close-all</button>
        </div>
      );
    }
    renderWithProviders(<SyncProbe />);
    fireEvent.click(screen.getByText('open'));
    expect(screen.getByTestId('active')).toHaveTextContent('job-a');
    // Simulate the user closing the pane via its X button.
    fireEvent.click(screen.getByText('remove-via-x'));
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
    expect(screen.getByTestId('active')).toHaveTextContent('none');
    // And via the Escape-style close-all path.
    fireEvent.click(screen.getByText('open'));
    expect(screen.getByTestId('active')).toHaveTextContent('job-a');
    fireEvent.click(screen.getByText('close-all'));
    expect(screen.getByTestId('active')).toHaveTextContent('none');
  });

  it('window title reflects job lifecycle status when provided', () => {
    function StatusProbe() {
      const { openLog, updateJobStatus } = useEvalLog();
      const { windows } = useSidePane();
      return (
        <div>
          <div data-testid="title">{windows[0]?.title || 'none'}</div>
          <button onClick={() => openLog('job-x', 'Run X', 'running')}>open-running</button>
          <button onClick={() => updateJobStatus('failed')}>fail</button>
          <button onClick={() => updateJobStatus('cancelled')}>cancel</button>
        </div>
      );
    }
    renderWithProviders(<StatusProbe />);
    fireEvent.click(screen.getByText('open-running'));
    expect(screen.getByTestId('title')).toHaveTextContent('log evaluation · running · job-x');
    fireEvent.click(screen.getByText('fail'));
    expect(screen.getByTestId('title')).toHaveTextContent('log evaluation · failed · job-x');
    fireEvent.click(screen.getByText('cancel'));
    expect(screen.getByTestId('title')).toHaveTextContent('log evaluation · cancelled · job-x');
  });
});
