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

  it('a shared entry merges with at most one local project (id beats URL, no duplicates)', () => {
    const shared = { id: 's1', name: 'pub', originUrl: 'https://github.com/org/pub', publishedAt: 100 };
    const localById = { id: 's1', name: 'pub-local', latestDate: 5 };
    const localByUrl = { id: 'other-id', name: 'pub2', originUrl: 'https://github.com/org/pub' };
    const merged = mergeProjects([localById, localByUrl], [shared]);
    assert.equal(merged.length, 2);
    const byId = merged.find((e) => e.local === localById);
    const byUrl = merged.find((e) => e.local === localByUrl);
    assert.equal(byId.chips, 'both');
    assert.equal(byId.shared, shared);
    assert.equal(byUrl.chips, 'local');
    assert.equal(byUrl.shared, null);
  });

  it('two locals with the same originUrl: first claims, second stays local-only', () => {
    const shared = { id: 'r1', name: 'lib', originUrl: 'https://github.com/org/lib', publishedAt: 3 };
    const local1 = { id: 'l1', name: 'lib', originUrl: 'https://github.com/org/lib' };
    const local2 = { id: 'l2', name: 'lib-fork', originUrl: 'https://github.com/org/lib' };
    const merged = mergeProjects([local1, local2], [shared]);
    assert.deepEqual(merged.map((e) => e.chips), ['both', 'local']);
    const sharedAttachedCount = merged.filter((e) => e.shared === shared).length;
    assert.equal(sharedAttachedCount, 1);
  });

  it('lastActivity of exactly 0 is preserved', () => {
    const localOnly = mergeProjects([{ id: 'a', name: 'app', latestDate: 0 }], []);
    assert.equal(localOnly[0].lastActivity, 0);

    const sharedOnly = mergeProjects([], [{ id: 'r1', name: 'lib', publishedAt: 0 }]);
    assert.equal(sharedOnly[0].lastActivity, 0);
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
  it('both sides same latestRunId -> in sync even if local eval is "newer" by date', () => {
    const e = entry(
      { id: 'a', latestDate: '2026-07-19T00:00:00Z', latestRunId: 'run-1' },
      { id: 'a', publishedAt: 1, latestRunId: 'run-1' },
    );
    assert.equal(deriveAction(e, { configured: true }), null);
  });
  it('differing latestRunId -> update, even same-day (the midnight-UTC bug)', () => {
    // Local's date-only eval parses to midnight UTC; shared published later
    // the same day. Old timestamp comparison would say "not newer" -> null.
    // Run identity must still win: different ids -> update.
    const e = entry(
      { id: 'a', latestDate: '2026-07-19', latestRunId: 'run-2' },
      { id: 'a', publishedAt: Date.parse('2026-07-19T14:00:00Z'), latestRunId: 'run-1' },
    );
    assert.equal(deriveAction(e, { configured: true }), 'update');
  });
  it('shared entry without latestRunId falls back to timestamp comparison', () => {
    const e = entry(
      { id: 'a', latestDate: '2026-07-19T00:00:00Z', latestRunId: 'run-1' },
      { id: 'a', publishedAt: 1 },
    );
    assert.equal(deriveAction(e, { configured: true }), 'update');
  });
});
