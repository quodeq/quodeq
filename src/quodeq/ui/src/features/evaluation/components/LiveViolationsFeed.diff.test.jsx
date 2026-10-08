import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import LiveViolationsFeed from './LiveViolationsFeed.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { getEvaluationProgress } from '../../../api/index.js';

// A PR review checks a handful of files. A clean one must not look empty:
// the feed says how many checks passed, per dimension and in total.
vi.mock('../../../api/index.js', () => ({ getEvaluationProgress: vi.fn() }));

function renderFeed(job) {
  const QC = withQueryClient();
  return render(<QC><LiveViolationsFeed job={job} liveViolations={{}} /></QC>);
}

const running = { jobId: 'ext-pr', status: 'running', source: 'external' };
const diffProgress = { dimensions: [
  { id: 'security', state: 'done', estimateReason: 'diff', files: { taken: 12, total: 12 }, compliance: 9 },
  { id: 'performance', state: 'pending', estimateReason: 'diff', files: { taken: 0, total: 9 }, compliance: null },
] };

describe('the live feed of a diff review', () => {
  beforeEach(() => { getEvaluationProgress.mockReset(); });

  it('the head counts the checks that passed', async () => {
    getEvaluationProgress.mockResolvedValue(diffProgress);
    renderFeed(running);
    expect(await screen.findByText('no new findings · 9 checks passed · streaming')).toBeInTheDocument();
  });

  it('an empty latest group says nothing was found and how much passed', async () => {
    getEvaluationProgress.mockResolvedValue(diffProgress);
    renderFeed(running);
    // Latest is open on entry.
    expect(await screen.findByText('no violations so far · 9 checks passed')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /latest/i }));
    expect(screen.queryByText('no violations so far · 9 checks passed')).toBeNull();
  });

  it('dimensions without findings show passed or queued', async () => {
    getEvaluationProgress.mockResolvedValue(diffProgress);
    renderFeed(running);
    expect(await screen.findByText('9 passed')).toBeInTheDocument();
    expect(screen.getByText('queued')).toBeInTheDocument();
  });

  it('a finished clean review still shows the feed', async () => {
    getEvaluationProgress.mockResolvedValue({ ...diffProgress, dimensions: diffProgress.dimensions.map((d) => ({ ...d, state: 'done', compliance: 4 })) });
    renderFeed({ ...running, status: 'done' });
    expect(await screen.findByText('no new findings · 8 checks passed')).toBeInTheDocument();
  });

  it('a full run keeps today\'s look', async () => {
    getEvaluationProgress.mockResolvedValue({ dimensions: [{ id: 'security', state: 'done', compliance: 9, files: { taken: 3, total: 3 } }] });
    renderFeed(running);
    await screen.findByText('no new findings · streaming');
    expect(screen.queryByText(/checks passed/)).toBeNull();
    expect(screen.queryByText('9 passed')).toBeNull();
  });
});
