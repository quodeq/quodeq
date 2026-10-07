import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { invalidateDimensionCache } from '../hooks/usePluginDimensions.js';
import { makeFakeApi, renderCard } from './_reEvaluateCard.fixtures.jsx';

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
});
