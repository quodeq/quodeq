import test from 'node:test';
import assert from 'node:assert/strict';
import { buildNavigationBundle } from './navigationBundle.js';
import { STEP_REPO_SCAN, STEP_WELCOME } from '../features/onboarding/wizardSteps.js';
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
  bundle.onTakeTour();
  bundle.onResumeSetup('p1');
  assert.equal(toasts.length, 3);
});

test('buildNavigationBundle entries carry where the wizard was opened from', () => {
  const entries = [];
  const bundle = buildNavigationBundle(args({ projects: [{ id: 'a' }], handleImportProject: () => {} }, {
    setWizardEntry: (e) => entries.push(e),
  }));
  bundle.onAddProject();
  bundle.onTakeTour();
  bundle.onTakeTour(WIZARD_SOURCE.SETTINGS);
  assert.deepEqual(entries.map((e) => [e.startStep, e.source, e.isFirstProject]), [
    [STEP_REPO_SCAN, WIZARD_SOURCE.ADD, false],
    [STEP_WELCOME, WIZARD_SOURCE.ADD, false],
    [STEP_WELCOME, WIZARD_SOURCE.SETTINGS, false],
  ]);
  // The welcome's "or import an exported archive" runs the bundle's guarded import.
  assert.equal(entries[1].onImportProject, bundle.onImportProject);
});

test('buildNavigationBundle opens the welcome as a first project when there are none', () => {
  const entries = [];
  const bundle = buildNavigationBundle(args({ projects: [] }, { setWizardEntry: (e) => entries.push(e) }));
  bundle.onTakeTour();
  assert.equal(entries[0].isFirstProject, true);
});
