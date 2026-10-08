import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { invalidateDimensionCache } from '../hooks/usePluginDimensions.js';
import { makeFakeApi, renderCard } from './_reEvaluateCard.fixtures.jsx';

vi.mock('../hooks/useScanData.js', () => ({
  useScanData: () => ({ scanData: { codeFiles: 3926, languages: { py: 2335 } }, loading: false, error: null }),
}));
vi.mock('../hooks/useScanEstimates.js', () => ({
  useScanEstimates: () => ({
    loading: false,
    estimates: { projectFiles: 3892, changedFiles: 3892, dimensions: {
      security: { count: 0, total: 3892, cached: 3892 },
      reliability: { count: 3892, total: 3892, cached: 0 },
    } },
  }),
}));

// The card wires the estimates through to the dimension cards: a dimension
// with nothing to analyze is muted on the real setup card.
describe('ReEvaluateCard up-to-date dimensions', () => {
  beforeEach(() => { invalidateDimensionCache(); });

  it('mutes the card whose dimension has nothing to analyze', async () => {
    const info = { name: 'demo', path: '/repos/myproj', location: 'local', ephemeral: false, evaluable: true };
    const api = makeFakeApi({
      getProjectInfo: vi.fn().mockResolvedValue(info),
      listPlugins: vi.fn().mockResolvedValue([{ dimensions: [
        { id: 'security', label: 'Security' }, { id: 'reliability', label: 'Reliability' },
      ] }]),
    });
    renderCard({ project: 'p-uptodate', projectInfo: info, api });
    await waitFor(() => expect(screen.getByRole('button', { name: /security/i })).toHaveClass('eval-dim-card--uptodate'));
    expect(screen.getByRole('button', { name: /reliability/i })).not.toHaveClass('eval-dim-card--uptodate');
  });

  it('shows the one file count the estimates give', async () => {
    const info = { name: 'demo', path: '/repos/myproj', location: 'local', ephemeral: false, evaluable: true };
    renderCard({ project: 'p-count', projectInfo: info, api: makeFakeApi({ getProjectInfo: vi.fn().mockResolvedValue(info) }) });
    await waitFor(() => expect(document.querySelector('.eval-detected-line')).toHaveTextContent(/^3,892 source files/));
  });

  it('enters with nothing selected, whatever the project ran last', async () => {
    const info = { name: 'demo', path: '/repos/myproj', location: 'local', ephemeral: false, evaluable: true, latestRunDimensions: ['reliability'] };
    const api = makeFakeApi({
      getProjectInfo: vi.fn().mockResolvedValue(info),
      listPlugins: vi.fn().mockResolvedValue([{ dimensions: [
        { id: 'security', label: 'Security' }, { id: 'reliability', label: 'Reliability' },
      ] }]),
    });
    renderCard({ project: 'p-none', projectInfo: info, api });
    await waitFor(() => expect(screen.getByRole('button', { name: /reliability/i })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /reliability/i })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: /security/i })).toHaveAttribute('aria-pressed', 'false');
    expect(document.querySelector('.eval-dims-counter')).toHaveTextContent('0 of 2 selected');
  });
});
