import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import RebuildStrip from './RebuildStrip.jsx';
import { RescoreTrackerContext } from '../grade-formula/rescore/RescoreTrackerContext.js';
import { recordWarmupSnapshot } from './warmupSnapshot.js';
import { DONE_LINGER_MS } from './useRebuildStatus.js';

vi.mock('../../api/index.js', () => ({ rescoreGradeFormula: vi.fn() }));
import { rescoreGradeFormula } from '../../api/index.js';

function mount({ rescore, target = null, warmup = null, track = vi.fn() } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (warmup) recordWarmupSnapshot(client, warmup);
  const tracker = { rescore, target, track, subscribe: () => () => {} };
  const ui = (value) => createElement(
    QueryClientProvider, { client },
    createElement(RescoreTrackerContext.Provider, { value }, createElement(RebuildStrip)),
  );
  const view = render(ui(tracker));
  return { ...view, client, track, rerenderWith: (value) => view.rerender(ui({ ...tracker, ...value })) };
}

afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

describe('RebuildStrip', () => {
  it('renders nothing while nothing runs', () => {
    mount({ rescore: { state: 'idle', done: 0, total: 0 }, warmup: { active: false } });
    expect(screen.queryByTestId('rebuild-strip')).toBeNull();
  });

  it('a tracked formula pass shows the counts and a determinate bar', () => {
    mount({ rescore: { state: 'running', generation: 2, done: 412, total: 1980 }, target: 2 });
    expect(screen.getByText('rescoring')).toBeTruthy();
    expect(screen.getByText('412 of 1980 runs…')).toBeTruthy();
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('21');
    expect(screen.getByRole('status').textContent).toBe('Rescoring runs with the new formula');
  });

  it('a pass still listing its runs shows an indeterminate bar', () => {
    mount({ rescore: { state: 'running', generation: 1, done: 0, total: 0 }, target: 1 });
    expect(screen.getByText('listing runs…')).toBeTruthy();
    expect(screen.getByRole('progressbar').getAttribute('aria-busy')).toBe('true');
  });

  it('the warm-up after an update names the project being rebuilt', () => {
    mount({ warmup: { active: true, projectsDone: 2, projectsTotal: 12, currentProjectName: 'quodeq' } });
    expect(screen.getByText('rebuilding scores')).toBeTruthy();
    expect(screen.getByText('2 of 12 projects · quodeq now…')).toBeTruthy();
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('17');
  });

  it('when the pass lands the strip says scores are up to date for a beat, then hides', () => {
    vi.useFakeTimers();
    const { rerenderWith } = mount({ rescore: { state: 'running', generation: 2, done: 10, total: 40 }, target: 2 });
    rerenderWith({ rescore: { state: 'idle', generation: 2, appliedGeneration: 2, done: 40, total: 40 }, target: null });
    expect(screen.getByText('scores up to date', { selector: '.rebuild-strip__label' })).toBeTruthy();
    expect(screen.getByText('40 runs rescored')).toBeTruthy();
    expect(screen.queryByRole('progressbar')).toBeNull();
    act(() => { vi.advanceTimersByTime(DONE_LINGER_MS); });
    expect(screen.queryByTestId('rebuild-strip')).toBeNull();
  });

  it('a failed pass stays with a retry that runs the pass again and hands it to the tracker', async () => {
    const payload = { rescore: { state: 'running', generation: 3, done: 0, total: 0 } };
    rescoreGradeFormula.mockResolvedValue(payload);
    const { track } = mount({ rescore: { state: 'error', generation: 2, done: 3, total: 9 } });
    expect(screen.getByText('rescore failed')).toBeTruthy();
    expect(screen.getByText('Some runs may still show the old formula.', { selector: '.sync-strip__meta' })).toBeTruthy();
    const retry = screen.getByRole('button', { name: 'retry' });
    await act(async () => { retry.click(); });
    await waitFor(() => expect(track).toHaveBeenCalledWith(payload));
    expect(rescoreGradeFormula).toHaveBeenCalledTimes(1);
  });

  it('a retry that fails logs and leaves the failed row with its retry enabled', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    rescoreGradeFormula.mockRejectedValue(new Error('offline'));
    mount({ rescore: { state: 'error', generation: 2, done: 0, total: 0 } });
    await act(async () => { screen.getByRole('button', { name: 'retry' }).click(); });
    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: 'retry' }).disabled).toBe(false);
    warn.mockRestore();
  });
});
