import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  META_COMMANDS, parseMetaCommand, matchCommands, buildMetaResponse, pillsForView,
} from './commands.js';

const catalog = {
  commands: META_COMMANDS,
  skills: [
    { name: 'explain-score', description: 'Explain a dimension score', argumentHint: '[dimension]', views: ['overview', 'violations'] },
    { name: 'create-standard', description: 'Draft a custom standard', argumentHint: '', views: ['standards'] },
  ],
  actions: [{ type: 'create_standard', description: 'Draft a new custom standard.' }],
};

test('parseMetaCommand recognizes reserved names only', () => {
  assert.equal(parseMetaCommand('/help'), 'help');
  assert.equal(parseMetaCommand('  /clear  '), 'clear');
  assert.equal(parseMetaCommand('/help me please'), 'help');
  assert.equal(parseMetaCommand('/explain-score'), null);
  assert.equal(parseMetaCommand('hello'), null);
});

test('matchCommands filters by prefix, empty after a space', () => {
  assert.deepEqual(matchCommands(catalog, '/ex').map((c) => c.name), ['explain-score']);
  const all = matchCommands(catalog, '/');
  assert.equal(all.length, META_COMMANDS.length + 2);
  assert.deepEqual(matchCommands(catalog, '/explain-score sec'), []);
  assert.deepEqual(matchCommands(null, '/he').map((c) => c.name), ['help']);
});

test('buildMetaResponse renders markdown catalogs', () => {
  assert.match(buildMetaResponse('skills', catalog), /\/explain-score/);
  assert.match(buildMetaResponse('actions', catalog), /create_standard/);
  assert.match(buildMetaResponse('help', catalog), /\/help/);
  assert.match(buildMetaResponse('help', null), /\/help/); // catalog fetch failed: still useful
});

test('pillsForView picks skills matching the view, max 4', () => {
  const pills = pillsForView(catalog, 'overview');
  assert.deepEqual(pills.map((p) => p.fill), ['/explain-score ']);
  assert.equal(pills[0].label, 'Explain score');
  assert.deepEqual(pillsForView(catalog, 'map'), []);
  assert.deepEqual(pillsForView(null, 'overview'), []);
});
