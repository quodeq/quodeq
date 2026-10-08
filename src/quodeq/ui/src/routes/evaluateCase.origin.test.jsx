import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Suspense } from 'react';

// A PR review is filed under a throwaway project in CI; the Evaluate route
// resolves it to the known project with the same git origin.
const job = { jobId: 'ext-pr', status: 'running', source: 'external', outputProject: 'tmp-uuid', originUrl: 'https://github.com/quodeq/quodeq' };

vi.mock('../features/evaluation/EvaluationLiveContext.jsx', () => ({
  useLiveJob: () => job,
  useLiveJobError: () => null,
  useLiveFindings: () => ({}),
  useLiveStartedProject: () => null,
  useEvaluationActions: () => ({}),
}));

vi.mock('../features/evaluation/components/EvaluateScreen.jsx', () => ({
  default: ({ context }) => <span>{context.jobProjectInfo?.name ?? 'none'}</span>,
}));

const { EvaluateCase } = await import('./routeCases.jsx');

describe('the Evaluate route and an external run', () => {
  it('names the project that shares the run\'s git origin', async () => {
    const projects = [{ id: 'p1', name: 'quodeq', originUrl: 'git@github.com:quodeq/quodeq.git' }];
    render(<Suspense fallback={null}><EvaluateCase selectedProject={null} projects={projects} /></Suspense>);
    expect(await screen.findByText('quodeq')).toBeInTheDocument();
  });
});
