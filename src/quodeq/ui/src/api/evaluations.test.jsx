import { describe, it, expect } from 'vitest';
import { runEventsUrl } from './evaluations.js';

describe('runEventsUrl', () => {
  it('points at the run events endpoint under the API base', () => {
    expect(runEventsUrl('job-123')).toBe('/api/evaluations/job-123/events');
  });
});
