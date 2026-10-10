import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { rowAction, rowLocation, rowSync, childEntry, ROW_LOCATION, ROW_RELOCATE, SYNC_STATE } from './projectRowModel.js';

const local = (extra = {}) => ({ id: 'p', name: 'p', location: 'local', ...extra });

describe('projectRowModel', () => {
  it('a missing folder offers relocate before anything else', () => {
    const entry = { local: local({ pathExists: false }), shared: null, chips: 'local', action: 'publish' };
    assert.equal(rowAction(entry), ROW_RELOCATE);
    assert.equal(rowLocation(entry), ROW_LOCATION.MISSING);
  });

  it('publish, update and pull follow the merged entry', () => {
    assert.equal(rowAction({ local: local(), shared: null, action: 'publish' }), 'publish');
    assert.equal(rowAction({ local: local(), shared: {}, action: 'update' }), 'update');
    assert.equal(rowAction({ local: null, shared: { id: 's' }, action: 'pull' }), 'pull');
    assert.equal(rowAction({ local: local(), shared: {}, action: null }), null);
  });

  it('an update on a project on both sides means the server copy is behind', () => {
    assert.equal(rowSync({ local: local(), shared: { publishedAt: 1 }, chips: 'both', action: 'update' }).state, SYNC_STATE.BEHIND);
    assert.deepEqual(rowSync({ local: local(), shared: { publishedAt: 1 }, chips: 'both', action: null }), { state: SYNC_STATE.PUBLISHED, publishedAt: 1 });
    assert.equal(rowSync({ local: local(), shared: null, chips: 'local', action: 'publish' }).state, SYNC_STATE.NONE);
    assert.equal(rowLocation({ local: null, shared: {} }), ROW_LOCATION.REMOTE);
  });

  it('a subproject without a merged entry reads as local only', () => {
    const entry = childEntry(local({ id: 'c' }), new Map());
    assert.equal(entry.key, 'c');
    assert.equal(entry.shared, null);
    assert.equal(entry.action, null);
  });
});
