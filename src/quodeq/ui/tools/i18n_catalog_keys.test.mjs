// The missing-key check in check_strings.mjs is only as good as the key
// extractor: a call shape it cannot see is a typo it cannot catch.
import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogKeyRefs } from './i18n_rules.mjs';

test('t() and tRich() yield their key', () => {
  assert.deepEqual([...catalogKeyRefs("t('a.b')")], ['a.b']);
  assert.deepEqual([...catalogKeyRefs("tRich( 'a.b', { x })")], ['a.b']);
});

test('pluralKey() yields both of its keys', () => {
  assert.deepEqual([...catalogKeyRefs("t(pluralKey(n, 'x.one', 'x.many'), { count: n })")], ['x.one', 'x.many']);
});

test('keys built at runtime and look-alike calls yield nothing', () => {
  assert.deepEqual([...catalogKeyRefs('t(key); format(\'a.b\'); tx(\'a.b\')')], []);
});
