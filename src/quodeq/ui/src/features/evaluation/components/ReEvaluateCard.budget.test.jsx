import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { invalidateDimensionCache } from '../hooks/usePluginDimensions.js';
import { makeFakeApi, renderCard } from './_reEvaluateCard.fixtures.jsx';

/**
 * Split from ReEvaluateCard.test.jsx: time budget copy and preselection
 * seeding.
 */

describe('ReEvaluateCard time budget copy', () => {
  beforeEach(() => { invalidateDimensionCache(); });

  const localInfo = { name: 'demo', path: '/repos/myproj', location: 'local', ephemeral: false, evaluable: true };
  const apiWithDims = () => makeFakeApi({
    getProjectInfo: vi.fn().mockResolvedValue(localInfo),
    listPlugins: vi.fn().mockResolvedValue([{ dimensions: [
      { id: 'security', label: 'Security' },
    ] }]),
  });

  it('describes the budget as a total for the run, not per dimension', async () => {
    renderCard({ project: 'p-budget', projectInfo: localInfo, api: apiWithDims() });
    await waitFor(() => expect(screen.getByText('time budget')).toBeInTheDocument());
    expect(screen.getByText(/total for the run/i)).toBeInTheDocument();
    expect(screen.queryByText(/per dimension/i)).not.toBeInTheDocument();
  });

  it('summarizes a picked budget as the run total, never "each"', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const user = userEvent.setup();
    renderCard({ project: 'p-budget2', projectInfo: localInfo, api: apiWithDims(), preselectDims: ['security'] });
    await waitFor(() => expect(screen.getByRole('button', { name: /security/i })).toHaveAttribute('aria-pressed', 'true'));

    await user.click(screen.getByRole('button', { name: '10:00' }));

    expect(screen.getByText(/10:00 total budget/)).toBeInTheDocument();
    expect(screen.queryByText(/budget each/)).not.toBeInTheDocument();
  });
});

describe('ReEvaluateCard preselection seeding', () => {
  beforeEach(() => { invalidateDimensionCache(); });

  const localInfo = { name: 'demo', path: '/repos/myproj', location: 'local', ephemeral: false, evaluable: true };
  const apiWithDims = () => makeFakeApi({
    getProjectInfo: vi.fn().mockResolvedValue(localInfo),
    listPlugins: vi.fn().mockResolvedValue([{ dimensions: [
      { id: 'security', label: 'Security' },
      { id: 'maintainability', label: 'Maintainability' },
    ] }]),
  });

  it('preselects the matching chip from preselectDims (case-insensitive)', async () => {
    renderCard({ project: 'p1', projectInfo: localInfo, api: apiWithDims(), preselectDims: ['Security'] });
    await waitFor(() => expect(screen.getByRole('button', { name: /security/i })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /security/i })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /maintainability/i })).toHaveAttribute('aria-pressed', 'false');
  });

  it('ignores ids with no matching chip and leaves selection empty', async () => {
    renderCard({ project: 'p2', projectInfo: localInfo, api: apiWithDims(), preselectDims: ['nonexistent'] });
    await waitFor(() => expect(screen.getByRole('button', { name: /security/i })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /security/i })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: /maintainability/i })).toHaveAttribute('aria-pressed', 'false');
  });

  it('leaves selection empty when preselectDims is empty (plain launch)', async () => {
    renderCard({ project: 'p3', projectInfo: localInfo, api: apiWithDims(), preselectDims: [] });
    await waitFor(() => expect(screen.getByRole('button', { name: /security/i })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /security/i })).toHaveAttribute('aria-pressed', 'false');
  });
});
