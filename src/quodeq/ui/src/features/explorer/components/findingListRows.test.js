import test from 'node:test';
import assert from 'node:assert/strict';
import { ROW_KIND, rowKeyGetter, rowSizeEstimator } from './findingListRows.js';

const HEIGHTS = { missing: 1, header: 2, row: 3 };

test('rowKeyGetter keys headers itself and hands every other row to findingKey', () => {
  const items = [{ kind: ROW_KIND.SEV_HEADER, sev: 'major' }, { kind: ROW_KIND.COMPLIANCE_HEADER }, { kind: 'v', id: 'x' }];
  const key = rowKeyGetter(items, (item, i) => `${item.id}@${i}`);
  assert.deepEqual([key(0), key(1), key(2)], ['h-major', 'h-compliance', 'x@2']);
});

test('rowKeyGetter falls back to the index for a row not materialised yet', () => {
  assert.equal(rowKeyGetter([], () => 'never')(4), 4);
});

test('rowSizeEstimator gives header rows, the low-confidence toggle included, the header height', () => {
  const items = [{ kind: ROW_KIND.SEV_HEADER }, { kind: ROW_KIND.COMPLIANCE_HEADER }, { kind: ROW_KIND.LOW_CONF_TOGGLE }];
  const size = rowSizeEstimator(items, HEIGHTS);
  assert.deepEqual([size(0), size(1), size(2)], [2, 2, 2]);
});

test('rowSizeEstimator gives findings the row height and unknown rows the missing height', () => {
  const size = rowSizeEstimator([{ kind: ROW_KIND.LOW_CONF_ROW }, { kind: 'v' }], HEIGHTS);
  assert.deepEqual([size(0), size(1), size(2)], [3, 3, 1]);
});
