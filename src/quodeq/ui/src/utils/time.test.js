import test from 'node:test';
import assert from 'node:assert/strict';
import { MS_PER_DAY } from './time.js';

// Every "days between" / "N days ago" computation in the UI multiplies or
// divides by MS_PER_DAY. Pin the value so a typo in the factor product does
// not silently shift compare windows and staleness thresholds; the compare
// fixtures deliberately spell 86400000 themselves rather than import this.
test('MS_PER_DAY is one day in milliseconds', () => {
  assert.equal(MS_PER_DAY, 86400000);
});
