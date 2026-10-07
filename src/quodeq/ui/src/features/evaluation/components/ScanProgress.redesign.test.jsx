import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { EvalLogContext } from '../eval-log/EvalLogContext.js';
import ScanProgress from './ScanProgress.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { getEvaluationProgress } from '../../../api/index.js';

vi.mock('../../../api/index.js', () => ({ getEvaluationProgress: vi.fn() }));

// The progress block is one bar for this run plus two pill buttons; the
// rest (the run, the repository's figures, the dimensions) waits behind
// "details", collapsed.
const ctx = { activeJobId: null, status: 'idle', openLog: vi.fn(), closeLog: vi.fn(), updateJobStatus: vi.fn() };
const progress = {
  state: 'running', projectFiles: 3892, budgetS: 600, totalElapsedS: 214, dimensions: [
    { id: 'reliability', state: 'done', files: { taken: 52, total: 52 }, filesCached: 3840, compliance: 1271, violations: 66 },
    { id: 'usability', state: 'running', files: { taken: 20, total: 52 }, filesCached: 3840, compliance: 610, violations: 12 },
  ],
};

function renderProgress(job) {
  const QC = withQueryClient();
  return render(<QC><EvalLogContext.Provider value={ctx}><ScanProgress job={job} /></EvalLogContext.Provider></QC>);
}

describe('the run progress block', () => {
  beforeEach(() => { getEvaluationProgress.mockReset(); getEvaluationProgress.mockResolvedValue(progress); });

  it('shows one run bar with details and console pills, and no coverage block', async () => {
    renderProgress({ jobId: 'j1', status: 'running', logs: [] });
    expect(await screen.findByRole('button', { name: /details/i })).toHaveClass('eval-pill-btn');
    expect(screen.getByRole('button', { name: /console/i })).toHaveClass('eval-pill-btn');
    expect(screen.queryByText(/repository coverage/i)).toBeNull();
    expect(document.querySelector('.scan-progress__foot-summary')).toBeNull();
  });

  it('details holds the run, the repository figures and the dimensions', async () => {
    renderProgress({ jobId: 'job-123', status: 'running', logs: [], commitSha: 'ed0e84baaff3', startedAt: '2026-10-07T17:36:29Z', deadlineAt: '2026-10-07T17:46:29Z' });
    fireEvent.click(await screen.findByRole('button', { name: /details/i }));
    expect(screen.getByText('job-123')).toBeInTheDocument();
    expect(screen.getByText('ed0e84b')).toBeInTheDocument();
    expect(screen.getByText('3,892')).toBeInTheDocument();
    expect(screen.getByText('1,881')).toBeInTheDocument(); // checks passed: 1271 + 610
    expect(screen.getByText('usability')).toBeInTheDocument();
  });

  it('details stays collapsed until asked', async () => {
    renderProgress({ jobId: 'job-123', status: 'running', logs: [] });
    expect(await screen.findByRole('button', { name: /details/i })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('job-123')).toBeNull();
  });

  it('per-dimension sums are labelled file-analyses, not files', async () => {
    // 52 + 20 analyzed, 0 + 32 to go: counts over dimensions, which a
    // "source files" figure beside them must not be read against.
    renderProgress({ jobId: 'job-1', status: 'running', logs: [] });
    fireEvent.click(await screen.findByRole('button', { name: /details/i }));
    expect(screen.getByText('file-analyses this run')).toBeInTheDocument();
    expect(screen.getByText('file-analyses to go')).toBeInTheDocument();
  });
});
