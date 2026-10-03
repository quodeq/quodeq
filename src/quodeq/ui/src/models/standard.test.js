import test from 'node:test';
import assert from 'node:assert/strict';
import { slugify, shouldSyncIdFromName, applyNameChange } from './standard.js';

// ---------------------------------------------------------------------------
// slugify
// ---------------------------------------------------------------------------

test('slugify: lowercases, collapses non-alnum runs to a single dash', () => {
  assert.equal(slugify('Clean Architecture!'), 'clean-architecture');
});

test('slugify: trims leading/trailing dashes', () => {
  assert.equal(slugify('  --Foo Bar--  '), 'foo-bar');
});

// ---------------------------------------------------------------------------
// shouldSyncIdFromName
// ---------------------------------------------------------------------------

test('shouldSyncIdFromName: true for a brand-new standard', () => {
  assert.equal(shouldSyncIdFromName({ id: '', name: '' }, true), true);
});

test('shouldSyncIdFromName: true when there is no id yet', () => {
  assert.equal(shouldSyncIdFromName({ id: '', name: 'Foo' }, false), true);
});

// An existing standard's id is its storage key: the PUT goes to
// /api/standards/<id>, so re-syncing it on rename sends the update to an id
// that does not exist (404) and the rename is lost.
test('shouldSyncIdFromName: false for an existing standard even when the id equals the slug of its name', () => {
  assert.equal(shouldSyncIdFromName({ id: 'foo-bar', name: 'Foo Bar' }, false), false);
});

test('shouldSyncIdFromName: false once the id has manually diverged from the name slug', () => {
  assert.equal(shouldSyncIdFromName({ id: 'custom-id', name: 'Foo Bar' }, false), false);
});

// ---------------------------------------------------------------------------
// applyNameChange
// ---------------------------------------------------------------------------

test('applyNameChange: syncs id for a new standard', () => {
  assert.deepEqual(
    applyNameChange({ id: '', name: '' }, 'Security', true),
    { name: 'Security', id: 'security' },
  );
});

test('applyNameChange: does not include id once the user has diverged it', () => {
  const updates = applyNameChange({ id: 'custom-id', name: 'Old Name' }, 'New Name', false);
  assert.deepEqual(updates, { name: 'New Name' });
  assert.ok(!('id' in updates));
});

test('applyNameChange: renaming an existing standard keeps its id', () => {
  const updates = applyNameChange({ id: 'accessibility', name: 'Accessibility' }, 'Accessibility v2', false);
  assert.deepEqual(updates, { name: 'Accessibility v2' });
});
