import { describe, it, expect } from 'vitest';
import { sessionKey } from './useAssistantSession.js';

// vitest, not node:test: useAssistantSession.js's import chain reaches
// api/request.js, which reads import.meta.env (a Vite-ism plain node can't
// resolve) — same reason mergeMessages.test.jsx tests one pure export of a
// .jsx file under vitest instead of node:test.
//
// Was duplicated verbatim at startSession and resetConversation call sites
// before this extraction — both must format an identical key for the same
// context, or startSession's dedupe check silently breaks.
describe('sessionKey', () => {
  it('joins provider/model/projectId/runId/source', () => {
    expect(sessionKey({ provider: 'claude', model: 'sonnet', projectId: 'p1', runId: 'r1', source: 'shared' }))
      .toBe('claude:sonnet:p1:r1:shared');
  });

  it('defaults source to "local" when absent', () => {
    expect(sessionKey({ provider: 'claude', model: 'sonnet', projectId: 'p1', runId: 'r1' }))
      .toBe('claude:sonnet:p1:r1:local');
  });

  it('two contexts differing only by source produce distinct keys', () => {
    const base = { provider: 'claude', model: 'sonnet', projectId: 'p1', runId: 'r1' };
    expect(sessionKey({ ...base, source: 'shared' })).not.toBe(sessionKey({ ...base, source: 'local' }));
  });

  it('handles a missing/undefined ctx without throwing', () => {
    expect(sessionKey(undefined)).toBe('undefined:undefined:undefined:undefined:local');
  });
});
