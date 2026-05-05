import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import EvaluationStatus from './EvaluationStatus.jsx';

vi.mock('./LiveViolationsFeed.jsx', () => ({ default: () => null }));
vi.mock('./ScanProgress.jsx', () => ({ default: () => null }));
vi.mock('./JobStatStrip.jsx', () => ({ default: () => null }));

function renderWithClient(ui) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const baseJob = {
  jobId: 'ext-test',
  status: 'done',
  source: 'external',
  logs: [],
  dimensions: [],
};

describe('StatusPill', () => {
  it('renders plain status text for a done run', () => {
    renderWithClient(<EvaluationStatus job={{ ...baseJob, status: 'done' }} />);
    const chip = document.querySelector('.term-status-pill');
    expect(chip.textContent).toBe('done');
    expect(chip.className).not.toContain('term-status-pill--stale');
  });

  it('renders "cancelled (stale)" with --stale class when exitReason starts with "stale_"', () => {
    renderWithClient(<EvaluationStatus job={{ ...baseJob, status: 'cancelled', exitReason: 'stale_detected' }} />);
    const chip = document.querySelector('.term-status-pill');
    expect(chip.textContent).toBe('cancelled (stale)');
    expect(chip.className).toContain('term-status-pill--stale');
    expect(chip.getAttribute('title')).toBe('stale_detected');
  });

  it('renders plain "cancelled" for user-initiated cancel (signal)', () => {
    renderWithClient(<EvaluationStatus job={{ ...baseJob, status: 'cancelled', exitReason: 'signal_SIGTERM' }} />);
    const chip = document.querySelector('.term-status-pill');
    expect(chip.textContent).toBe('cancelled');
    expect(chip.className).not.toContain('term-status-pill--stale');
    expect(chip.getAttribute('title')).toBe('signal_SIGTERM');
  });

  it('renders "failed" with tooltip showing exception reason', () => {
    renderWithClient(<EvaluationStatus job={{ ...baseJob, status: 'failed', exitReason: 'exception: EvaluationError' }} />);
    const chip = document.querySelector('.term-status-pill');
    expect(chip.textContent).toBe('failed');
    expect(chip.className).not.toContain('term-status-pill--stale');
    expect(chip.getAttribute('title')).toBe('exception: EvaluationError');
  });
});

describe('ExternalRunBadge', () => {
  it('renders "External" when job.source is "external"', () => {
    renderWithClient(<EvaluationStatus job={{ ...baseJob, source: 'external' }} />);
    expect(screen.getByText('External')).toBeInTheDocument();
  });

  it('renders nothing for source="internal"', () => {
    renderWithClient(<EvaluationStatus job={{ ...baseJob, source: 'internal' }} />);
    expect(screen.queryByText('External')).toBeNull();
    expect(screen.queryByText('Running outside the dashboard')).toBeNull();
  });
});
