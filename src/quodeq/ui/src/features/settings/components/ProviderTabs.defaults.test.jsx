import { describe, it, expect } from 'vitest';
import { defaultsForProvider } from './providerUtils.js';

// Truth-in-display: the Settings tab must show the values a run would
// actually use. Cloud providers without a bespoke entry used to fall back
// to the generic hook defaults (1 subagent / Unlimited) while the start
// payload ran them with 5 / 600s.
describe('defaultsForProvider', () => {
  it('cli providers: concurrent subagents with the 10-minute cap', () => {
    expect(defaultsForProvider('cli', 'claude')).toMatchObject({
      subagents: '5',
      'time-limit': '600',
    });
  });

  it('generic cloud providers get the same effective defaults as the payload', () => {
    expect(defaultsForProvider('cloud-api', 'some-new-cloud')).toMatchObject({
      subagents: '5',
      'time-limit': '600',
    });
  });

  it('openrouter keeps its bespoke model default on top of the cloud fallback', () => {
    const d = defaultsForProvider('cloud-api', 'openrouter');
    expect(d).toMatchObject({ subagents: '5', 'time-limit': '600' });
    expect(d.model).toBeTruthy();
  });

  it('local-api providers stay at unlimited', () => {
    for (const id of ['ollama', 'llamacpp', 'omlx']) {
      expect(defaultsForProvider('local-api', id)).toMatchObject({ 'time-limit': '0' });
    }
  });
});
