import { test } from 'node:test';
import assert from 'node:assert/strict';
import { balancedColumns } from './useBalancedColumns.js';

test('one row when every card fits', () => {
  assert.equal(balancedColumns(7, 1300, 160, 12), 7);
});

test('spreads the overflow evenly: 9 cards that fit 8 become 5 + 4', () => {
  assert.equal(balancedColumns(9, 1360, 160, 12), 5);
});

test('three rows of 3 for 9 cards that fit 4 across', () => {
  assert.equal(balancedColumns(9, 700, 160, 12), 3);
});

test('no layout before measuring or with nothing to place', () => {
  assert.equal(balancedColumns(0, 1000, 160, 12), null);
  assert.equal(balancedColumns(5, 0, 160, 12), null);
});
