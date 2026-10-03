import { describe, it, expect, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { dropRunFromProjectQueries } from './useDashboardInvalidation.js';
import { projectKeys } from '../../../api/queryKeys.js';

const P = 'proj-a';
const row = (runId) => ({ runId, dateISO: '2026-09-01', overallScore: '7.0' });

function seed(client) {
  client.setQueryData(projectKeys.dashboard(P, null), { trend: [row('A'), row('B')], partialRuns: [row('B')], selectedRun: { runId: 'A' } });
  client.setQueryData(projectKeys.dashboard(P, 'B'), { trend: [row('A'), row('B')], partialRuns: [] });
  client.setQueryData(projectKeys.scores(P, null), { trend: [row('A'), row('B')], availableRuns: [row('A'), row('B')], accumulated: { x: 1 } });
  client.setQueryData(projectKeys.scores(P, 'B'), { trend: [row('B')], availableRuns: [row('B')] });
  client.setQueryData(projectKeys.dashboard('proj-z', null), { trend: [row('B')] });
  client.setQueryData(projectKeys.gradeExplain(P, 'B', 'security'), null);
  client.setQueryData(projectKeys.runs(P), [row('B')]);
}

describe('dropRunFromProjectQueries', () => {
  it('removes the run from every trend/partialRuns/availableRuns under the project', () => {
    const client = new QueryClient();
    seed(client);
    dropRunFromProjectQueries(client, P, 'local', 'B');
    expect(client.getQueryData(projectKeys.dashboard(P, null))).toEqual({ trend: [row('A')], partialRuns: [], selectedRun: { runId: 'A' } });
    expect(client.getQueryData(projectKeys.dashboard(P, 'B'))).toEqual({ trend: [row('A')], partialRuns: [] });
    expect(client.getQueryData(projectKeys.scores(P, null))).toEqual({ trend: [row('A')], availableRuns: [row('A')], accumulated: { x: 1 } });
    expect(client.getQueryData(projectKeys.scores(P, 'B'))).toEqual({ trend: [], availableRuns: [] });
  });

  it('does not touch another project', () => {
    const client = new QueryClient();
    seed(client);
    dropRunFromProjectQueries(client, P, 'local', 'B');
    expect(client.getQueryData(projectKeys.dashboard('proj-z', null))).toEqual({ trend: [row('B')] });
  });

  it('leaves non-object and array data untouched', () => {
    const client = new QueryClient();
    seed(client);
    dropRunFromProjectQueries(client, P, 'local', 'B');
    expect(client.getQueryData(projectKeys.gradeExplain(P, 'B', 'security'))).toBeNull();
    expect(client.getQueryData(projectKeys.runs(P))).toEqual([row('B')]);
  });

  it('does not touch the state of queries the run was not in', () => {
    const client = new QueryClient();
    seed(client);
    const key = projectKeys.gradeExplain(P, 'B', 'security');
    const before = client.getQueryState(key).dataUpdateCount;
    const untouchedKey = projectKeys.dashboard(P, 'C');
    client.setQueryData(untouchedKey, { trend: [row('A')] });
    const untouchedBefore = client.getQueryState(untouchedKey).dataUpdateCount;
    dropRunFromProjectQueries(client, P, 'local', 'B');
    expect(client.getQueryState(key).dataUpdateCount).toBe(before);
    expect(client.getQueryState(untouchedKey).dataUpdateCount).toBe(untouchedBefore);
  });

  it('cancels fetches in flight under the project so a stale reply cannot re-add the run', () => {
    const client = new QueryClient();
    seed(client);
    const cancel = vi.spyOn(client, 'cancelQueries');
    dropRunFromProjectQueries(client, P, 'local', 'B');
    expect(cancel).toHaveBeenCalledWith({ queryKey: projectKeys.project(P, 'local') });
  });
});
