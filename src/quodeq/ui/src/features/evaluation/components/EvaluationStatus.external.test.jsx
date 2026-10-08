import { render, screen, fireEvent } from '@testing-library/react';
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
vi.mock('../../updates/openExternal.js', () => ({ openExternal: vi.fn() }));
import { openExternal } from '../../updates/openExternal.js';

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
  beforeEach(() => { getEvaluationProgress.mockReset(); });

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

const prDone = { ...external, status: 'done', originUrl: 'https://github.com/quodeq/quodeq.git' };

describe('the end of a PR review', () => {
  beforeEach(() => { getEvaluationProgress.mockReset(); openExternal.mockReset(); });

  it('points to the pull request and opens the commit on GitHub', async () => {
    getEvaluationProgress.mockResolvedValue(diff);
    render(<QueryClientProvider client={new QueryClient()}><EvaluationStatus job={prDone} onDismiss={vi.fn()} /></QueryClientProvider>);
    fireEvent.click(await screen.findByRole('button', { name: /open on github/i }));
    expect(openExternal).toHaveBeenCalledWith('https://github.com/quodeq/quodeq/commit/7e506ae1234');
    expect(screen.getByText('the review is posted on the pull request')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /view results/i })).toBeNull();
    expect(screen.getByRole('button', { name: /close/i })).toHaveClass('eval-pill-btn');
  });

  it('a review whose folder vanished reads as ended, not lost', async () => {
    getEvaluationProgress.mockResolvedValue(diff);
    renderJob({ ...prDone, status: 'done', vanished: true });
    expect(await screen.findByText('evaluation_ended')).toBeInTheDocument();
    expect(screen.getByText('ended')).toHaveClass('eval-run-pill--neutral');
    expect(await screen.findByRole('button', { name: /open on github/i })).toBeInTheDocument();
    // Its ending is unknown: it may never have reached the post step.
    expect(screen.getByText('results go to the pull request')).toBeInTheDocument();
    expect(screen.queryByText('the review is posted on the pull request')).toBeNull();
  });

  it('a review stopped from the app never claims it was posted', async () => {
    getEvaluationProgress.mockResolvedValue(diff);
    renderJob({ ...prDone, status: 'cancelled' });
    expect(await screen.findByRole('button', { name: /open on github/i })).toBeInTheDocument();
    expect(screen.queryByText(/pull request/)).toBeNull();
  });

  it('a vanished run that was not a review offers close only', async () => {
    getEvaluationProgress.mockResolvedValue(full);
    renderJob({ ...prDone, status: 'done', vanished: true });
    expect(await screen.findByText('evaluation_ended')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /view results/i })).toBeNull();
  });

  it('a finished nightly keeps view results', async () => {
    getEvaluationProgress.mockResolvedValue(full);
    renderJob({ ...prDone });
    expect(await screen.findByRole('button', { name: /view results/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /open on github/i })).toBeNull();
  });

  it('no GitHub origin, no open on GitHub', async () => {
    getEvaluationProgress.mockResolvedValue(diff);
    renderJob({ ...prDone, originUrl: 'https://gitlab.com/a/b' });
    await screen.findByText('the review is posted on the pull request');
    expect(screen.queryByRole('button', { name: /open on github/i })).toBeNull();
  });
});

describe('a run that recorded where it came from', () => {
  beforeEach(() => { getEvaluationProgress.mockReset(); openExternal.mockReset(); });
  const pr = { kind: 'ci', event: 'pull_request', pr: 1402, prUrl: 'https://github.com/quodeq/quodeq/pull/1402' };

  it('a PR review is named by its pull request and opens it', async () => {
    getEvaluationProgress.mockResolvedValue(diff);
    renderJob({ ...prDone, origin: pr });
    expect(await screen.findByText('PR review #1402')).toHaveClass('eval-run-tag');
    expect(screen.queryByText(/diff review/)).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: /open on github/i }));
    expect(openExternal).toHaveBeenCalledWith('https://github.com/quodeq/quodeq/pull/1402');
  });

  it('the nightly is named nightly', async () => {
    getEvaluationProgress.mockResolvedValue(full);
    renderJob({ ...external, origin: { kind: 'ci', event: 'schedule', workflow: 'Quodeq Nightly' } });
    expect(await screen.findByText('nightly')).toHaveClass('eval-run-tag');
  });
});
