import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mergeProjects, deriveAction, normalizeOriginUrl } from './projectsMerge.js';

describe('normalizeOriginUrl', () => {
  it('trims .git suffix and trailing slash', () => {
    assert.equal(normalizeOriginUrl('https://x/y.git'), 'https://x/y');
    assert.equal(normalizeOriginUrl('https://x/y/'), 'https://x/y');
    assert.equal(normalizeOriginUrl(null), null);
  });
});

describe('mergeProjects', () => {
  it('merges by id first', () => {
    const merged = mergeProjects(
      [{ id: 'a', name: 'app', latestDate: '2026-07-18', latestScore: 7.2 }],
      [{ id: 'a', name: 'app', publishedAt: 1752600000000 }],
    );
    assert.equal(merged.length, 1);
    assert.equal(merged[0].chips, 'both');
  });

  it('merges by originUrl when ids differ, tolerant of .git suffix', () => {
    const merged = mergeProjects(
      [{ id: 'local-1', name: 'app', originUrl: 'https://github.com/org/app' }],
      [{ id: 'remote-9', name: 'app', originUrl: 'https://github.com/org/app.git', publishedAt: 1 }],
    );
    assert.equal(merged.length, 1);
    assert.equal(merged[0].chips, 'both');
  });

  it('does NOT merge on name alone', () => {
    const merged = mergeProjects(
      [{ id: 'l1', name: 'app', originUrl: 'https://github.com/you/app' }],
      [{ id: 'r1', name: 'app', originUrl: 'https://github.com/org/app', publishedAt: 1 }],
    );
    assert.equal(merged.length, 2);
    assert.deepEqual(merged.map((e) => e.chips).sort(), ['local', 'shared']);
  });

  it('keeps unmatched shared entries as shared-only', () => {
    const merged = mergeProjects([], [{ id: 'r1', name: 'lib', publishedAt: 5 }]);
    assert.equal(merged[0].chips, 'shared');
    assert.equal(merged[0].key, 'r1');
  });

  it('computes lastActivity as max(local eval, publishedAt) and prefers local score', () => {
    const merged = mergeProjects(
      [{ id: 'a', name: 'app', latestDate: '2026-07-19T00:00:00Z', latestScore: 6.8 }],
      [{ id: 'a', name: 'app', publishedAt: 1, latestScore: 8.0 }],
    );
    assert.equal(merged[0].lastActivity, Date.parse('2026-07-19T00:00:00Z'));
    assert.equal(merged[0].score, 6.8);
  });
});

describe('deriveAction', () => {
  const entry = (local, shared) => ({ local, shared });
  it('local only -> publish when configured, hidden otherwise', () => {
    assert.equal(deriveAction(entry({ id: 'a' }, null), { configured: true }), 'publish');
    assert.equal(deriveAction(entry({ id: 'a' }, null), { configured: false }), null);
  });
  it('shared only -> pull', () => {
    assert.equal(deriveAction(entry(null, { id: 'a' }), { configured: true }), 'pull');
  });
  it('both, local newer -> update', () => {
    const e = entry({ id: 'a', latestDate: '2026-07-19T00:00:00Z' }, { id: 'a', publishedAt: 1 });
    assert.equal(deriveAction(e, { configured: true }), 'update');
  });
  it('both, in sync -> null', () => {
    const e = entry(
      { id: 'a', latestDate: '2026-07-10T00:00:00Z' },
      { id: 'a', publishedAt: Date.parse('2026-07-19T00:00:00Z') },
    );
    assert.equal(deriveAction(e, { configured: true }), null);
  });
});
