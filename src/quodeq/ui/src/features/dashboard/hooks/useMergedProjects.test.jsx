import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useMergedProjects } from './useMergedProjects.js';

const locals = [
  { id: 'a', name: 'alpha', latestDate: '2026-07-19T00:00:00Z', latestScore: 6.0 },
  { id: 'b', name: 'beta', latestDate: '2026-07-10T00:00:00Z', latestScore: 9.0 },
];
const shareds = [
  { id: 'a', name: 'alpha', publishedAt: 1, latestScore: 7.0 },
  { id: 'c', name: 'gamma', publishedAt: Date.parse('2026-07-20T00:00:00Z'), latestScore: 8.0 },
];

function run(filters) {
  const { result } = renderHook(() =>
    useMergedProjects({ localProjects: locals, sharedProjects: shareds, configured: true, filters }),
  );
  return result.current;
}

describe('useMergedProjects', () => {
  it('defaults: sorted by lastActivity desc with derived actions', () => {
    const entries = run(undefined);
    expect(entries.map((e) => e.key)).toEqual(['c', 'a', 'b']);
    expect(entries.find((e) => e.key === 'a').action).toBe('update');
    expect(entries.find((e) => e.key === 'b').action).toBe('publish');
    expect(entries.find((e) => e.key === 'c').action).toBe('pull');
  });

  it('filters by location and by name substring', () => {
    expect(run({ location: 'local' }).map((e) => e.key)).toEqual(['a', 'b']);
    expect(run({ location: 'shared' }).map((e) => e.key).sort()).toEqual(['a', 'c']);
    expect(run({ query: 'gam' }).map((e) => e.key)).toEqual(['c']);
  });

  it('sorts by name and by score', () => {
    expect(run({ sort: 'name' }).map((e) => e.name)).toEqual(['alpha', 'beta', 'gamma']);
    expect(run({ sort: 'score' }).map((e) => e.key)).toEqual(['b', 'c', 'a']);
  });
});
