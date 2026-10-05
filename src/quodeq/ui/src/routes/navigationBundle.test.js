import test from 'node:test';
import assert from 'node:assert/strict';
import { buildNavigationBundle } from './navigationBundle.js';
import { STEP_ANALYZE, STEP_WELCOME, STEP_CONNECT } from '../features/onboarding/wizardSteps.js';
import { WIZARD_SOURCE } from '../features/onboarding/onboardingVocab.js';

function args(state, extra = {}) {
  return {
    state,
    navTab: () => {},
    navStackLength: 0,
    isEvaluating: false,
    showToast: () => {},
    setWizardEntry: () => {},
    ...extra,
  };
}

test('buildNavigationBundle forwards every state key, including ones added later', () => {
  // The finding this pins: a hand-maintained field list silently drops any
  // key a route renderer starts consuming (that is how the repositories
  // local/online tab flip broke on handleNavigateReplace).
  const state = {
    selectedProject: 'p1',
    handleNavigateReplace: () => {},
    aKeyAddedAfterThisBundleWasWritten: () => {},
  };
  const bundle = buildNavigationBundle(args(state));
  assert.equal(bundle.selectedProject, 'p1');
  assert.equal(bundle.handleNavigateReplace, state.handleNavigateReplace);
  assert.equal(bundle.aKeyAddedAfterThisBundleWasWritten, state.aKeyAddedAfterThisBundleWasWritten);
});

test('buildNavigationBundle forwards navTab, navStackLength and isEvaluating from the caller args', () => {
  const navTab = () => {};
  const bundle = buildNavigationBundle(args({ projects: [] }, { navTab, navStackLength: 3, isEvaluating: true }));
  assert.equal(bundle.navTab, navTab);
  assert.equal(bundle.navStackLength, 3);
  assert.equal(bundle.isEvaluating, true);
});

test('buildNavigationBundle derives the action handlers as functions', () => {
  const bundle = buildNavigationBundle(args({ projects: [] }));
  assert.equal(typeof bundle.onAddProject, 'function');
  assert.equal(typeof bundle.onImportProject, 'function');
  assert.equal(typeof bundle.onTakeTour, 'function');
  assert.equal(typeof bundle.onResumeSetup, 'function');
});

test('buildNavigationBundle sets onBrowseRemote to null by default', () => {
  const bundle = buildNavigationBundle(args({ projects: [] }));
  // Null (not a no-op handler) so consumers can hide the affordance.
  assert.equal(bundle.onBrowseRemote, null);
});

test('buildNavigationBundle sets onBrowseRemote to a function when sharedHasContent is true', () => {
  const bundle = buildNavigationBundle(args({}, { sharedHasContent: true }));
  assert.equal(typeof bundle.onBrowseRemote, 'function');
});

test('buildNavigationBundle keeps the caller-owned fields when state carries the same names', () => {
  const bundle = buildNavigationBundle(args({ isEvaluating: true, navStackLength: 99, onBrowseRemote: 'stale' }));
  assert.equal(bundle.isEvaluating, false);
  assert.equal(bundle.navStackLength, 0);
  assert.equal(bundle.onBrowseRemote, null);
});

test('buildNavigationBundle action handlers short-circuit while evaluating', () => {
  const toasts = [];
  const setWizardEntry = () => { throw new Error('must not run while evaluating'); };
  const bundle = buildNavigationBundle(args({ projects: [] }, {
    isEvaluating: true, showToast: (m) => toasts.push(m), setWizardEntry,
  }));
  bundle.onAddProject();
  bundle.onStartAnalyze();
  bundle.onTakeTour();
  bundle.onResumeSetup('p1');
  assert.equal(toasts.length, 4);
});

test('add project opens the add panel directly, never the welcome', () => {
  const entries = [];
  const bundle = buildNavigationBundle(args({ projects: [{ id: 'a' }], handleImportProject: () => {} }, {
    setWizardEntry: (e) => entries.push(e),
  }));
  bundle.onAddProject();
  assert.equal(entries[0].startStep, STEP_ANALYZE);
  assert.equal(entries[0].source, WIZARD_SOURCE.ADD);
  assert.equal(entries[0].isFirstProject, false);
  assert.equal(bundle.onAddProject, bundle.onStartAnalyze);
});

test('onStartAnalyze opens the analyze screen directly, never the welcome again', () => {
  const entries = [];
  const bundle = buildNavigationBundle(args({ projects: [] }, { setWizardEntry: (e) => entries.push(e) }));
  bundle.onStartAnalyze();
  assert.equal(entries.length, 1);
  assert.equal(entries[0].startStep, STEP_ANALYZE);
  assert.equal(entries[0].source, WIZARD_SOURCE.ADD);
});

test('buildNavigationBundle entries carry where the wizard was opened from', () => {
  const entries = [];
  const bundle = buildNavigationBundle(args({ projects: [{ id: 'a' }], handleImportProject: () => {} }, {
    setWizardEntry: (e) => entries.push(e),
  }));
  const reselect = () => {};
  bundle.onAddProject();
  bundle.onTakeTour();
  bundle.onTakeTour(WIZARD_SOURCE.SETTINGS, reselect);
  assert.deepEqual(entries.map((e) => [e.startStep, e.source, e.isFirstProject]), [
    [STEP_ANALYZE, WIZARD_SOURCE.ADD, false],
    [STEP_WELCOME, WIZARD_SOURCE.ADD, false],
    [STEP_WELCOME, WIZARD_SOURCE.SETTINGS, false],
  ]);
  // The welcome's archive card runs the bundle's guarded import; its
  // connected card's disconnect hands the app's reselect along.
  assert.equal(entries[1].onImportProject, bundle.onImportProject);
  assert.equal(entries[2].onSharedDisconnected, reselect);
});

test('buildNavigationBundle opens the welcome as a first project when there are none', () => {
  const entries = [];
  const bundle = buildNavigationBundle(args({ projects: [] }, { setWizardEntry: (e) => entries.push(e) }));
  bundle.onTakeTour();
  assert.equal(entries[0].isFirstProject, true);
});

test('an import that lands goes to the repositories tab and selects the imported project', async () => {
  const navs = [];
  const picks = [];
  const bundle = buildNavigationBundle(args({
    projects: [{ id: 'a' }], selectedProject: 'a', activeTab: 'overview',
    handleImportProject: async () => ({ ok: true, projectId: 'p-imp' }),
    handleProjectChange: (...call) => picks.push(call),
  }, { navTab: (tab) => navs.push(tab) }));
  await bundle.onImportProject();
  assert.deepEqual(navs, ['projects']);
  assert.deepEqual(picks, [['p-imp', 'local']]);
});

test('a cancelled or failed import stays where it was', async () => {
  const navs = [];
  const bundle = buildNavigationBundle(args({
    projects: [{ id: 'a' }], handleImportProject: async () => ({ ok: false, cancelled: true }),
  }, { navTab: (tab) => navs.push(tab) }));
  await bundle.onImportProject();
  assert.deepEqual(navs, []);
});

test('onConnectEvaluations opens the wizard on the connect step', () => {
  const entries = [];
  const bundle = buildNavigationBundle(args({ projects: [{ id: 'a' }], handleImportProject: () => {} }, {
    setWizardEntry: (e) => entries.push(e),
  }));
  bundle.onConnectEvaluations();
  assert.equal(entries.length, 1);
  assert.equal(entries[0].startStep, STEP_CONNECT);
  assert.equal(entries[0].source, WIZARD_SOURCE.CONNECT);
  assert.equal(entries[0].onImportProject, bundle.onImportProject);
});
