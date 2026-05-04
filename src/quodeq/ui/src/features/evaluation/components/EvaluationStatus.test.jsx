import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import EvaluationStatus from './EvaluationStatus.jsx';

// Mock child components so we isolate what we care about.
vi.mock('./LiveViolationsFeed.jsx', () => ({ default: () => null }));
vi.mock('./ScanProgress.jsx', () => ({ default: () => null }));

const baseJob = {
  jobId: 'ext-test',
  status: 'done',
  source: 'external',
  logs: [],
  dimensions: [],
};

describe('StatusChip', () => {
  it('renders plain status text for a done run', () => {
    render(<EvaluationStatus job={{ ...baseJob, status: 'done' }} />);
    const chip = document.querySelector('.job-status-badge');
    expect(chip.textContent).toBe('done');
    expect(chip.className).not.toContain('job-status-badge--stale');
  });

  it('renders "cancelled (stale)" with --stale class when exitReason starts with "stale_"', () => {
    render(<EvaluationStatus job={{ ...baseJob, status: 'cancelled', exitReason: 'stale_detected' }} />);
    const chip = document.querySelector('.job-status-badge');
    expect(chip.textContent).toBe('cancelled (stale)');
    expect(chip.className).toContain('job-status-badge--stale');
    expect(chip.getAttribute('title')).toBe('stale_detected');
  });

  it('renders plain "cancelled" for user-initiated cancel (signal)', () => {
    render(<EvaluationStatus job={{ ...baseJob, status: 'cancelled', exitReason: 'signal_SIGTERM' }} />);
    const chip = document.querySelector('.job-status-badge');
    expect(chip.textContent).toBe('cancelled');
    expect(chip.className).not.toContain('job-status-badge--stale');
    expect(chip.getAttribute('title')).toBe('signal_SIGTERM');
  });

  it('renders "failed" with tooltip showing exception reason', () => {
    render(<EvaluationStatus job={{ ...baseJob, status: 'failed', exitReason: 'exception: EvaluationError' }} />);
    const chip = document.querySelector('.job-status-badge');
    expect(chip.textContent).toBe('failed');
    expect(chip.className).not.toContain('job-status-badge--stale');
    expect(chip.getAttribute('title')).toBe('exception: EvaluationError');
  });
});

describe('JobHeader escape hatch', () => {
  it('renders a Hide button alongside Cancel when status is running', () => {
    render(<EvaluationStatus job={{ ...baseJob, status: 'running' }} onCancel={() => {}} onDismiss={() => {}} />);
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /hide/i })).toBeInTheDocument();
  });

  it('clicking Hide on a running job calls onDismiss with "close"', () => {
    const onDismiss = vi.fn();
    render(<EvaluationStatus job={{ ...baseJob, status: 'running' }} onCancel={() => {}} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole('button', { name: /hide/i }));
    expect(onDismiss).toHaveBeenCalledWith('close');
  });

  it('does not render Hide for a done job (Dismiss already covers it)', () => {
    render(<EvaluationStatus job={{ ...baseJob, status: 'done' }} onCancel={() => {}} onDismiss={() => {}} />);
    expect(screen.queryByRole('button', { name: /^hide$/i })).toBeNull();
  });
});

describe('ExternalRunBadge', () => {
  it('renders "External" when job.source is "external"', () => {
    render(<EvaluationStatus job={{ ...baseJob, source: 'external' }} />);
    expect(screen.getByText('External')).toBeInTheDocument();
  });

  it('renders nothing for source="internal"', () => {
    render(<EvaluationStatus job={{ ...baseJob, source: 'internal' }} />);
    expect(screen.queryByText('External')).toBeNull();
    expect(screen.queryByText('Running outside the dashboard')).toBeNull();
  });
});
