import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import CountdownTimer from './CountdownTimer.jsx';

describe('CountdownTimer', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('renders nothing when deadline is null and budget is 0 (unlimited)', () => {
    const { container } = render(<CountdownTimer deadlineAt={null} budgetSeconds={0} phase="analyzing" />);
    expect(container.firstChild).toBeNull();
  });

  it('shows greyed static budget during preparing', () => {
    render(<CountdownTimer deadlineAt={null} budgetSeconds={600} phase="preparing" />);
    const el = screen.getByTestId('eval-countdown');
    expect(el).toHaveTextContent('10:00');
    expect(el).toHaveClass('eval-countdown--idle');
  });

  it('counts down from deadline_at', () => {
    const now = Date.now();
    vi.setSystemTime(now);
    const deadline = new Date(now + 90_000).toISOString();
    render(<CountdownTimer deadlineAt={deadline} budgetSeconds={600} phase="analyzing" />);
    expect(screen.getByTestId('eval-countdown')).toHaveTextContent('1:30');
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(screen.getByTestId('eval-countdown')).toHaveTextContent('0:30');
  });

  it('switches to alert color in last 30s', () => {
    const now = Date.now();
    vi.setSystemTime(now);
    const deadline = new Date(now + 25_000).toISOString();
    render(<CountdownTimer deadlineAt={deadline} budgetSeconds={600} phase="analyzing" />);
    expect(screen.getByTestId('eval-countdown')).toHaveClass('eval-countdown--alert');
  });

  it('freezes at 0:00 instead of going negative', () => {
    const now = Date.now();
    vi.setSystemTime(now);
    const deadline = new Date(now - 10_000).toISOString();
    render(<CountdownTimer deadlineAt={deadline} budgetSeconds={600} phase="analyzing" />);
    expect(screen.getByTestId('eval-countdown')).toHaveTextContent('0:00');
  });

  it('hides on terminal phase', () => {
    const now = Date.now();
    vi.setSystemTime(now);
    const deadline = new Date(now + 60_000).toISOString();
    const { container } = render(<CountdownTimer deadlineAt={deadline} budgetSeconds={600} phase="done" />);
    expect(container.firstChild).toBeNull();
  });
});
