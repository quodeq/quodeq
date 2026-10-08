import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import EvaluationStatus from './EvaluationStatus.jsx';
import { getEvaluationProgress } from '../../../api/index.js';
import { formatRunTime } from '../../../utils/dateFormatting.js';

// A run this app did not start: the header says so, the strip says when it
// started and on which commit, and a PR review reads as a diff review.
vi.mock('./ScanProgress.jsx', () => ({ default: () => null }));
vi.mock('./JobStatStrip.jsx', () => ({ default: () => null }));
vi.mock('../../../api/index.js', () => ({ getEvaluationProgress: vi.fn() }));

function renderJob(job) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><EvaluationStatus job={job} /></QueryClientProvider>);
}

const started = '2026-10-08T06:12:00Z';
const external = { jobId: 'ext-r', status: 'running', source: 'external', logs: [], dimensions: [], startedAt: started, commitSha: '7e506ae1234' };
const full = { projectFiles: 3892, dimensions: [{ id: 'security', state: 'running', files: { taken: 3, total: 52 }, filesCached: 3840 }] };
const diff = { dimensions: [
  { id: 'security', state: 'running', estimateReason: 'diff', files: { taken: 3, total: 12 }, filesCached: 0 },
  { id: 'performance', state: 'pending', estimateReason: 'diff', files: { taken: 0, total: 9 }, filesCached: 0 },
] };

describe('the run screen for an external run', () => {
  beforeEach(() => getEvaluationProgress.mockReset());

  it('a run the app started has no external tag or started cell', async () => {
    getEvaluationProgress.mockResolvedValue(full);
    renderJob({ ...external, source: 'internal' });
    await screen.findByText('repository');
    expect(screen.queryByText('external')).toBeNull();
    expect(screen.queryByText('started')).toBeNull();
  });

  it('an external run says so and when it started, on which commit', async () => {
    getEvaluationProgress.mockResolvedValue(full);
    renderJob(external);
    expect(await screen.findByText('external')).toHaveClass('eval-run-tag');
    expect(screen.getByText('started')).toBeInTheDocument();
    expect(screen.getByText(new RegExp(formatRunTime(started)))).toBeInTheDocument();
    expect(screen.getByText(/7e506ae$/)).toBeInTheDocument();
  });

  it('a PR review reads as a diff review over its changed files', async () => {
    getEvaluationProgress.mockResolvedValue(diff);
    renderJob(external);
    expect(await screen.findByText('external · diff review')).toBeInTheDocument();
    expect(screen.getByText('diff · 12 files')).toBeInTheDocument();
  });
});
