import { describe, it, expect } from 'vitest';
import { bucketBySeverity } from './principleFiltering.js';

// The File page's buckets are rebuilt from the hydrated rows; a severity the
// vocabulary does not know (or none at all) lands in the unknown bucket,
// exactly where the original aggregation put it, never dropped and never
// promoted to minor.
describe('bucketBySeverity', () => {
  it('keeps unknown and missing severities in the unknown bucket', () => {
    const rows = [
      { file: 'a.py', severity: 'Critical' },
      { file: 'b.py', severity: 'info' },
      { file: 'c.py' },
      { file: 'd.py', severity: 'minor' },
    ];
    const buckets = bucketBySeverity(rows);
    expect(buckets.critical.map((v) => v.file)).toEqual(['a.py']);
    expect(buckets.minor.map((v) => v.file)).toEqual(['d.py']);
    expect(buckets.unknown.map((v) => v.file)).toEqual(['b.py', 'c.py']);
    expect(Object.values(buckets).flat()).toHaveLength(rows.length);
  });
});
