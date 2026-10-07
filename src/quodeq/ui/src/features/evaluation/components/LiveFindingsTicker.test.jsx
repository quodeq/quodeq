import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import LiveFindingsTicker from './LiveFindingsTicker.jsx';
import { latestFindings, addPin } from './liveTicker.js';

const f = (arrivalSeq, title, severity = 'major') => ({ arrivalSeq, title, severity, principle: 'p', file: `${title}.swift`, line: 1 });
const titles = () => Array.from(document.querySelectorAll('.vticker-row .vrow-rule')).map((n) => n.textContent);

describe('latestFindings', () => {
  it('takes the newest across dimensions, newest first', () => {
    const rows = latestFindings({ security: [f(1, 'a'), f(4, 'd')], reliability: [f(2, 'b'), f(3, 'c')] }, 3);
    expect(rows.map((r) => r.v.title)).toEqual(['d', 'c', 'b']);
    expect(rows[0].dim).toBe('security');
  });

  it('keeps at most the ticker size', () => {
    const many = { security: Array.from({ length: 40 }, (_, i) => f(i + 1, `t${i}`)) };
    expect(latestFindings(many)).toHaveLength(10);
  });
});

describe('addPin', () => {
  it('puts the newest pin first and drops the oldest past the cap', () => {
    const pins = ['a', 'b', 'c', 'd'].reduce((cur, key) => addPin(cur, { key }), []);
    expect(pins.map((p) => p.key)).toEqual(['d', 'c', 'b']);
  });

  it('ignores a pin that is already there', () => {
    const once = addPin([], { key: 'a' });
    expect(addPin(once, { key: 'a' })).toBe(once);
  });
});

describe('LiveFindingsTicker', () => {
  afterEach(() => { vi.useRealTimers(); });

  it('renders nothing without findings', () => {
    const { container } = render(<LiveFindingsTicker liveViolations={{}} isRunning />);
    expect(container.firstChild).toBeNull();
  });

  it('lists the latest findings newest first', () => {
    render(<LiveFindingsTicker liveViolations={{ security: [f(1, 'first'), f(2, 'second')] }} isRunning />);
    expect(titles()).toEqual(['second', 'first']);
    expect(screen.getByText('live')).toBeInTheDocument();
  });

  it('pins a clicked finding with its detail, and unpins it', () => {
    render(<LiveFindingsTicker liveViolations={{ security: [f(1, 'Crash on nil', 'critical')] }} isRunning={false} />);
    fireEvent.click(screen.getByRole('button', { name: /Pin critical finding: Crash on nil/ }));
    const pin = document.querySelector('.vticker-pin');
    expect(pin).not.toBeNull();
    expect(pin.querySelector('.vlive-detail')).not.toBeNull();
    expect(screen.getByRole('button', { name: /Pin critical finding/ })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Unpin finding' }));
    expect(document.querySelector('.vticker-pin')).toBeNull();
  });

  it('holds still while hovered and says how many are waiting', () => {
    vi.useFakeTimers();
    const { rerender } = render(<LiveFindingsTicker liveViolations={{ security: [f(1, 'first')] }} isRunning />);
    fireEvent.pointerEnter(document.querySelector('.vticker-card'));
    rerender(<LiveFindingsTicker liveViolations={{ security: [f(1, 'first'), f(2, 'second')] }} isRunning />);
    act(() => { vi.advanceTimersByTime(1000); });
    expect(titles()).toEqual(['first']);
    expect(screen.getByText('paused · 1 new waiting')).toBeInTheDocument();
    fireEvent.pointerLeave(document.querySelector('.vticker-card'));
    act(() => { vi.advanceTimersByTime(1000); });
    expect(titles()).toEqual(['second', 'first']);
  });
});
