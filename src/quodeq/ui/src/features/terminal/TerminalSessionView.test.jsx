import { describe, it, expect, vi } from 'vitest';
import { makeSocketOnOpen } from './TerminalSessionView.jsx';

// The reconnect-reset guard (makeSocketOnOpen) resets xterm before the
// server replays scrollback -- see the doc comment above it in
// TerminalSessionView.jsx. A throw here (e.g. a disposed terminal mid-flight)
// used to be swallowed silently, defeating that duplicate-scrollback fix
// with no trace. It must now log instead of disappearing.
describe('makeSocketOnOpen', () => {
  it('logs when term.reset() throws instead of swallowing it', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const term = {
      reset: vi.fn(() => { throw new Error('reset failed'); }),
      write: vi.fn(),
      options: {},
    };
    const termRef = { current: term };

    makeSocketOnOpen(termRef)();

    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('[TerminalSessionView]'),
      expect.any(Error),
    );
    // disableStdin must still be re-enabled even though reset() threw.
    expect(term.options.disableStdin).toBe(false);
  });

  it('re-enables input and writes the breathing-room line on success', () => {
    const term = { reset: vi.fn(), write: vi.fn(), options: { disableStdin: true } };
    const termRef = { current: term };

    makeSocketOnOpen(termRef)();

    expect(term.reset).toHaveBeenCalled();
    expect(term.write).toHaveBeenCalledWith('\r\n');
    expect(term.options.disableStdin).toBe(false);
  });
});
