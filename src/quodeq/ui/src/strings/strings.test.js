import test from 'node:test';
import assert from 'node:assert/strict';
import { t } from './index.js';

test('returns the catalog value for a known key', () => {
  assert.equal(t('updates.download'), 'download');
});

test('interpolates {placeholder} vars', () => {
  assert.equal(t('updates.available', { version: '1.9.0' }), 'Quodeq v1.9.0 is available.');
});

test('leaves unknown placeholders intact', () => {
  assert.equal(t('updates.available', { unrelated: 'x' }), 'Quodeq v{version} is available.');
});

test('returns the key itself when missing from the catalog', () => {
  assert.equal(t('nope.not.a.key'), 'nope.not.a.key');
});

test('coerces non-string vars', () => {
  assert.equal(t('updates.available', { version: 2 }), 'Quodeq v2 is available.');
});
