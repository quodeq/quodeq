import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import JobStatStrip from './JobStatStrip.jsx';

vi.mock('../../../api/index.js', () => ({
  getEvaluationProgress: vi.fn(),
}));
import { getEvaluationProgress } from '../../../api/index.js';

function renderWithClient(ui) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const runningJob = { jobId: 'job-1', status: 'running' };
const doneJob    = { jobId: 'job-2', status: 'done' };

describe('JobStatStrip', () => {
  beforeEach(() => { getEvaluationProgress.mockReset(); });

  it('renders 4 stat cells for a running job', async () => {
    getEvaluationProgress.mockResolvedValue({
      dimensions: [{ state: 'running', files: { taken: 138, total: 220 } }],
      totalElapsedS: 134,
    });
    renderWithClient(<JobStatStrip job={runningJob} liveViolations={{ security: [{}, {}] }} />);
    expect(await screen.findByText('STATUS')).toBeInTheDocument();
    expect(screen.getByText('PROGRESS')).toBeInTheDocument();
    expect(screen.getByText('FOUND')).toBeInTheDocument();
    expect(screen.getByText('ELAPSED')).toBeInTheDocument();
    // value cells
    expect(await screen.findByText('63%')).toBeInTheDocument();
    expect(screen.getByText('2:14')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();    // FOUND count
  });

  it('renders SCANNED + VIOLATIONS + DURATION for a done job', async () => {
    getEvaluationProgress.mockResolvedValue({
      dimensions: [{ state: 'done', files: { taken: 220, total: 220 } }],
      totalElapsedS: 272,
    });
    renderWithClient(<JobStatStrip job={doneJob} liveViolations={{ security: new Array(13).fill({}) }} />);
    expect(await screen.findByText('SCANNED')).toBeInTheDocument();
    expect(screen.getByText('VIOLATIONS')).toBeInTheDocument();
    expect(screen.getByText('DURATION')).toBeInTheDocument();
    expect(await screen.findByText('220')).toBeInTheDocument();
    expect(screen.getByText('13')).toBeInTheDocument();
    expect(screen.getByText('4:32')).toBeInTheDocument();
  });

  it('renders fallback values when progress query has no data yet', () => {
    getEvaluationProgress.mockResolvedValue(null);
    renderWithClient(<JobStatStrip job={runningJob} liveViolations={{}} />);
    // STATUS always renders
    expect(screen.getByText('STATUS')).toBeInTheDocument();
    expect(screen.getByText('running')).toBeInTheDocument();
  });

  it('returns null when job is missing', () => {
    const { container } = renderWithClient(<JobStatStrip job={null} liveViolations={{}} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows "estimating…" subtext for a fresh running job (one sample)', async () => {
    getEvaluationProgress.mockResolvedValue({
      dimensions: [{ state: 'running', files: { taken: 10, total: 1000 } }],
    });
    const job = { jobId: 'job-3', status: 'running', startedAt: new Date(Date.now() - 5000).toISOString() };
    renderWithClient(<JobStatStrip job={job} liveViolations={{}} />);
    expect(await screen.findByText('estimating…')).toBeInTheDocument();
  });

  it('ELAPSED reflects wall-clock from startedAt (not backend elapsed)', async () => {
    const now = new Date('2026-06-08T10:00:00Z').getTime();
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(now);
    getEvaluationProgress.mockResolvedValue({
      dimensions: [{ state: 'running', files: { taken: 10, total: 1000 } }],
      totalElapsedS: 9999, // would show 166:39 if backend value were used
    });
    const job = { jobId: 'job-4', status: 'running', startedAt: new Date(now - 5000).toISOString() };
    renderWithClient(<JobStatStrip job={job} liveViolations={{}} />);
    // Wait for the poll to resolve (PROGRESS shows 1%) so we assert the
    // post-resolution value: with the old code this would flip to backend
    // 9999s (166:39); the new code keeps wall-clock 0:05.
    expect(await screen.findByText('1%')).toBeInTheDocument();
    expect(screen.getByText('0:05')).toBeInTheDocument();
    nowSpy.mockRestore();
  });

  it('ELAPSED ticks forward each second', async () => {
    vi.useFakeTimers();
    try {
      const t0 = new Date('2026-06-08T10:00:00Z').getTime();
      vi.setSystemTime(t0);
      getEvaluationProgress.mockResolvedValue({
        dimensions: [{ state: 'running', files: { taken: 10, total: 1000 } }],
      });
      const job = { jobId: 'job-5', status: 'running', startedAt: new Date(t0 - 5000).toISOString() };
      renderWithClient(<JobStatStrip job={job} liveViolations={{}} />);
      await vi.advanceTimersByTimeAsync(0);     // flush the initial fetch
      expect(screen.getByText('0:05')).toBeInTheDocument();
      await vi.advanceTimersByTimeAsync(2000);  // two 1s ticks
      expect(screen.getByText('0:07')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
