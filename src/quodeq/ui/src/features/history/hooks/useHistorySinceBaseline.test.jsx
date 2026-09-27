import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useHistorySinceBaseline } from './useHistorySinceBaseline.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

const diff = { runId: 'r1', commitSha: 'abc1234def', dimensions: { maintainability: {
  counts: { new: 3, resolved: 4 }, majorsDelta: -1, types: { closed: ['M-A-1'], opened: [] }, againstRunId: 'r0', againstCommitSha: 'def',
  sinceBaseline: { scope: 'all', changedFiles: null, majorsDelta: -1, counts: { new: 3, resolved: 4 }, types: { closed: ['M-A-1'], opened: [] } },
} } };
const trend = [{ runId: 'r1', dateLabel: '2 Sep', status: 'done' }, { runId: 'r2', dateLabel: '3 Sep', status: 'running' }];

function Probe({ runId, selectedSource = PROJECT_SOURCE.LOCAL }) {
  const { since, selectedRun } = useHistorySinceBaseline({ project: 'p', selectedSource, runId, trend, dimensionNames: ['maintainability'], onNavigate: () => {} });
  return <pre data-testid="out">{JSON.stringify({ majorsDelta: since?.majorsDelta ?? null, sha: selectedRun?.commitSha ?? null })}</pre>;
}

function mount(api, props) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><ApiProvider value={api}><Probe {...props} /></ApiProvider></QueryClientProvider>);
}

describe('useHistorySinceBaseline', () => {
  it('fetches the highlighted run\'s diff and folds it', async () => {
    const getRunDiff = vi.fn(async () => diff);
    mount({ getRunDiff }, { runId: 'r1' });
    await screen.findByText(/"majorsDelta":-1/);
    expect(getRunDiff).toHaveBeenCalledWith('p', 'r1');
    expect(screen.getByTestId('out').textContent).toContain('"sha":"abc1234def"');
  });

  it('no request for a row that is not a finished trend run', async () => {
    const getRunDiff = vi.fn(async () => diff);
    mount({ getRunDiff }, { runId: 'r9' });
    mount({ getRunDiff }, { runId: 'r2' });
    await new Promise((r) => setTimeout(r, 0));
    expect(getRunDiff).not.toHaveBeenCalled();
  });

  it('no request on a shared project', async () => {
    const getRunDiff = vi.fn(async () => diff);
    mount({ getRunDiff }, { runId: 'r1', selectedSource: PROJECT_SOURCE.SHARED });
    await new Promise((r) => setTimeout(r, 0));
    expect(getRunDiff).not.toHaveBeenCalled();
  });
});
