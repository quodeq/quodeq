import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { SORT_KEY, SORT_DIR, naturalDirection, sortDirection, nextSort } from './projectsSort.js';

describe('projectsSort', () => {
  it('names start A to Z, everything else biggest or newest first', () => {
    assert.equal(naturalDirection(SORT_KEY.NAME), SORT_DIR.ASC);
    assert.equal(naturalDirection(SORT_KEY.SCORE), SORT_DIR.DESC);
    assert.equal(naturalDirection(SORT_KEY.FILES), SORT_DIR.DESC);
    assert.equal(naturalDirection(SORT_KEY.ACTIVITY), SORT_DIR.DESC);
  });

  it('defaults to last run, newest first', () => {
    assert.equal(sortDirection({}, SORT_KEY.ACTIVITY), SORT_DIR.DESC);
  });

  it('a new column starts in its natural direction; the active one flips', () => {
    assert.deepEqual(nextSort({ sort: SORT_KEY.ACTIVITY }, SORT_KEY.NAME), { sort: SORT_KEY.NAME, dir: SORT_DIR.ASC });
    assert.deepEqual(nextSort({ sort: SORT_KEY.SCORE, dir: SORT_DIR.DESC }, SORT_KEY.SCORE), { sort: SORT_KEY.SCORE, dir: SORT_DIR.ASC });
    assert.deepEqual(nextSort({}, SORT_KEY.ACTIVITY), { sort: SORT_KEY.ACTIVITY, dir: SORT_DIR.ASC });
  });
});
