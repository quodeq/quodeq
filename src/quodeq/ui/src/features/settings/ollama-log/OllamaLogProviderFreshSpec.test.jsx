import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { OllamaLogProvider } from './OllamaLogProvider.jsx';
import { useOllamaLog } from './OllamaLogContext.js';

// The side-pane's own replaceWindow(spec) effect (see useLogWindow.js) fires
// on the very next render too, using the by-then-updated stream status, so a
// render-based assertion taken after fireEvent.click settles cannot tell a
// correct fresh title from a briefly-wrong one that gets corrected a beat
// later — jsdom flushes that whole cascade inside one `act()`. Mocking
// addWindow lets this test read the exact spec openLog handed it
// synchronously, before any of that cascade has a chance to run.
const { addWindowSpy } = vi.hoisted(() => ({ addWindowSpy: vi.fn() }));

vi.mock('../../side-pane/SidePaneContext.jsx', () => ({
  useSidePane: () => ({
    addWindow: addWindowSpy,
    removeWindow: vi.fn(),
    replaceWindow: vi.fn(),
    hasWindow: () => true,
  }),
}));

// Mock EventSource so useOllamaLogStream doesn't throw (same shape as
// OllamaLogProvider.test.jsx's mock).
class MockEventSource {
  constructor(url) {
    this.url = url;
    this.readyState = 0;
  }
  addEventListener() {}
  removeEventListener() {}
  set onmessage(_fn) {}
  set onerror(_fn) {}
  close() { this.readyState = 2; }
}

function Probe() {
  const { openLog } = useOllamaLog();
  return <button onClick={openLog}>open</button>;
}

describe('OllamaLogProvider openLog fresh spec', () => {
  let originalEventSource;
  beforeEach(() => {
    originalEventSource = globalThis.EventSource;
    globalThis.EventSource = MockEventSource;
    addWindowSpy.mockClear();
  });
  afterEach(() => {
    globalThis.EventSource = originalEventSource;
    vi.restoreAllMocks();
  });

  it('adds the window with the running-status title immediately, not the bare idle title', () => {
    render(<OllamaLogProvider><Probe /></OllamaLogProvider>);
    fireEvent.click(screen.getByText('open'));
    expect(addWindowSpy).toHaveBeenCalledTimes(1);
    expect(addWindowSpy.mock.calls[0][0].title).toContain('· running');
  });
});
