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
});
