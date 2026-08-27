import { describe, it, expect } from 'vitest';
import { warmOverviewChunks } from './bootChunks.js';

// Boot lands on the Overview, so its lazy chunks (DashboardPage, and the
// recharts-heavy RunHistoryPanel) must start fetching at app mount — while
// the startup loader is still up — not when the page first renders. This
// pins that the warm list resolves: a moved/renamed chunk path would
// otherwise silently reintroduce the boot chart-placeholder flash.
describe('warmOverviewChunks', () => {
  it('resolves every overview boot chunk', async () => {
    const results = await warmOverviewChunks();
    expect(results.length).toBeGreaterThanOrEqual(2);
    for (const r of results) expect(r.status).toBe('fulfilled');
  });
});
