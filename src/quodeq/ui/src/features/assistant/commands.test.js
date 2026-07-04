import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  META_COMMANDS, VISIBLE_META_COMMANDS, parseMetaCommand, matchCommands,
  buildMetaResponse, pillsForView,
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
  assert.equal(parseMetaCommand('/actions'), 'actions'); // hidden but still answered locally
  assert.equal(parseMetaCommand('/explain-score'), null);
  assert.equal(parseMetaCommand('hello'), null);
});

test('matchCommands filters by prefix, empty after a space, hides hidden metas', () => {
  assert.deepEqual(matchCommands(catalog, '/ex').map((c) => c.name), ['explain-score']);
  const all = matchCommands(catalog, '/');
  assert.equal(all.length, VISIBLE_META_COMMANDS.length + 2);
  assert.deepEqual(matchCommands(catalog, '/ac'), []); // /actions never suggested
  assert.deepEqual(matchCommands(catalog, '/explain-score sec'), []);
  assert.deepEqual(matchCommands(null, '/he').map((c) => c.name), ['help']);
});

test('buildMetaResponse renders markdown catalogs', () => {
  assert.match(buildMetaResponse('skills', catalog), /\/explain-score/);
  assert.match(buildMetaResponse('actions', catalog), /create_standard/);
  assert.match(buildMetaResponse('help', catalog), /\/help/);
  assert.doesNotMatch(buildMetaResponse('help', catalog), /\/actions/); // hidden metas stay out of /help
  assert.match(buildMetaResponse('help', null), /\/help/); // catalog fetch failed: still useful
});

test('pillsForView leads with view-matching skills, then the rest, max 4', () => {
  const pills = pillsForView(catalog, 'overview');
  assert.deepEqual(pills.map((p) => p.fill), ['/explain-score ', '/create-standard ']);
  assert.equal(pills[0].label, 'Explain score');
  // standards view reorders: create-standard first, remaining skills after
  assert.deepEqual(pillsForView(catalog, 'standards').map((p) => p.fill),
    ['/create-standard ', '/explain-score ']);
  // no view match: every skill still offered, catalog order
  assert.deepEqual(pillsForView(catalog, 'map').map((p) => p.fill),
    ['/explain-score ', '/create-standard ']);
  assert.deepEqual(pillsForView(null, 'overview'), []);
});
