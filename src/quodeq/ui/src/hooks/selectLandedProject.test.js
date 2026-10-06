import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldSelectLanded, selectLandedProject } from './selectLandedProject.js';

test('a landed project is selected on the Repositories tab or when nothing is selected', () => {
  assert.equal(shouldSelectLanded({ activeTab: 'projects', selectedProject: 'other' }), true);
  assert.equal(shouldSelectLanded({ activeTab: 'overview', selectedProject: null }), true);
  assert.equal(shouldSelectLanded({ activeTab: 'overview', selectedProject: 'other' }), false);
  assert.equal(shouldSelectLanded({ activeTab: 'evaluate', selectedProject: 'other' }), false);
});

test('selectLandedProject selects as local, and does nothing without an id or off the tab', () => {
  const calls = [];
  const state = { activeTab: 'projects', selectedProject: 'other', handleProjectChange: (...args) => calls.push(args) };
  selectLandedProject(state, 'p-new');
  assert.deepEqual(calls, [['p-new', 'local']]);
  selectLandedProject(state, null);
  selectLandedProject({ ...state, activeTab: 'overview' }, 'p-new');
  assert.equal(calls.length, 1);
});
