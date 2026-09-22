import test from 'node:test';
import assert from 'node:assert/strict';
import {
  isEvaluatableSource, shouldShowEvaluateButton, shouldBounceToEvaluate,
  resolveProjectDisplayName, shouldShowProjectTabs, selectSidebarCounts,
  shouldRedirectToRemoteRepositories, shouldShowCompareTab,
} from './appGating.js';

// ---------------------------------------------------------------------------
// isEvaluatableSource
// ---------------------------------------------------------------------------

test('isEvaluatableSource: shared has no Evaluate flow', () => {
  assert.equal(isEvaluatableSource('shared'), false);
});

test('isEvaluatableSource: local is evaluatable', () => {
  assert.equal(isEvaluatableSource('local'), true);
});

test('isEvaluatableSource: an unset source defaults to evaluatable (Sidebar receives no projectsCount gate)', () => {
  assert.equal(isEvaluatableSource(undefined), true);
});

// ---------------------------------------------------------------------------
// shouldShowEvaluateButton — composed from isEvaluatableSource; identical
// truth table to before the recompose (TopBar's projectsCount gate PLUS the
// source gate; Sidebar deliberately has no projectsCount gate of its own —
// see Sidebar.test.jsx and the isEvaluatableSource case above).
// ---------------------------------------------------------------------------

test('shouldShowEvaluateButton: true only with projects AND a local-ish source', () => {
  assert.equal(shouldShowEvaluateButton(3, 'local'), true);
  assert.equal(shouldShowEvaluateButton(0, 'local'), false);
  assert.equal(shouldShowEvaluateButton(3, 'shared'), false);
  assert.equal(shouldShowEvaluateButton(0, 'shared'), false);
});

test('shouldShowEvaluateButton: a nullish projectsCount is treated as zero', () => {
  assert.equal(shouldShowEvaluateButton(null, 'local'), false);
  assert.equal(shouldShowEvaluateButton(undefined, 'local'), false);
});

// ---------------------------------------------------------------------------
// shouldBounceToEvaluate — untouched by this change; a couple of smoke
// cases so a future edit to appGating.js can't silently break it here too.
// ---------------------------------------------------------------------------

test('shouldBounceToEvaluate: fires only for a local project-data tab with no runs yet', () => {
  const base = {
    projectsLoaded: true, projectsCount: 1, selectedProjectInfo: { id: 'p1' },
    hasCurrentProjectRuns: false, activeTab: 'overview', selectedSource: 'local',
  };
  assert.equal(shouldBounceToEvaluate(base), true);
  assert.equal(shouldBounceToEvaluate({ ...base, selectedSource: 'shared' }), false);
  assert.equal(shouldBounceToEvaluate({ ...base, hasCurrentProjectRuns: true }), false);
  assert.equal(shouldBounceToEvaluate({ ...base, projectsLoaded: false }), false);
});

// ---------------------------------------------------------------------------
// resolveProjectDisplayName
// ---------------------------------------------------------------------------

test('resolveProjectDisplayName: prefers selectedProjectInfo displayName/name', () => {
  assert.equal(resolveProjectDisplayName({ selectedProjectInfo: { displayName: 'Foo' } }), 'Foo');
  assert.equal(resolveProjectDisplayName({ selectedProjectInfo: { name: 'Bar' } }), 'Bar');
});

test('resolveProjectDisplayName: falls back to sharedProjectInfo for a shared selection', () => {
  assert.equal(
    resolveProjectDisplayName({ selectedSource: 'shared', sharedProjectInfo: { name: 'Remote' } }),
    'Remote',
  );
});

test('resolveProjectDisplayName: guards against a raw UUID flashing as the name', () => {
  assert.equal(
    resolveProjectDisplayName({ selectedDisplayName: 'uuid-1', selectedProject: 'uuid-1' }),
    null,
  );
  assert.equal(
    resolveProjectDisplayName({ selectedDisplayName: 'My Project', selectedProject: 'uuid-1' }),
    'My Project',
  );
});

// ---------------------------------------------------------------------------
// shouldShowProjectTabs
// ---------------------------------------------------------------------------

test('shouldShowProjectTabs: local gates on hasCurrentProjectRuns', () => {
  assert.equal(shouldShowProjectTabs({ selectedSource: 'local', hasCurrentProjectRuns: true }), true);
  assert.equal(shouldShowProjectTabs({ selectedSource: 'local', hasCurrentProjectRuns: false }), false);
});

test('shouldShowProjectTabs: shared gates on sharedProjectInfo resolving', () => {
  assert.equal(shouldShowProjectTabs({ selectedSource: 'shared', sharedProjectInfo: { name: 'x' } }), true);
  assert.equal(shouldShowProjectTabs({ selectedSource: 'shared', sharedProjectInfo: null }), false);
});

// ---------------------------------------------------------------------------
// selectSidebarCounts
// ---------------------------------------------------------------------------

test('selectSidebarCounts: prefers the filtered numbers, falls back to unfiltered', () => {
  const counts = selectSidebarCounts({
    filteredAccumulated: { summary: { totalViolations: 5 } },
    accumulated: { summary: { totalViolations: 9 } },
    filteredTrend: [1, 2],
    dashboard: { trend: [1, 2, 3] },
  });
  assert.deepEqual(counts, { violationsCount: 5, historyCount: 2 });
});

test('selectSidebarCounts: nulls out immediately when nothing has landed yet', () => {
  assert.deepEqual(
    selectSidebarCounts({ filteredAccumulated: null, accumulated: null, filteredTrend: null, dashboard: null }),
    { violationsCount: null, historyCount: null },
  );
});

// ---------------------------------------------------------------------------
// shouldShowCompareTab
// ---------------------------------------------------------------------------

test('shouldShowCompareTab: hidden with zero or one local project with runs and no shared content', () => {
  assert.equal(shouldShowCompareTab({ projects: [], sharedHasContent: false }), false);
  assert.equal(shouldShowCompareTab({ projects: [{ runsCount: 3 }], sharedHasContent: false }), false);
});

test('shouldShowCompareTab: shown once two local projects have runs', () => {
  assert.equal(
    shouldShowCompareTab({ projects: [{ runsCount: 1 }, { runsCount: 2 }], sharedHasContent: false }),
    true,
  );
});

test('shouldShowCompareTab: one local project with runs plus shared content is enough', () => {
  assert.equal(shouldShowCompareTab({ projects: [{ runsCount: 1 }], sharedHasContent: true }), true);
});

test('shouldShowCompareTab: shared content alone (zero local projects with runs) is not enough', () => {
  assert.equal(shouldShowCompareTab({ projects: [], sharedHasContent: true }), false);
  assert.equal(shouldShowCompareTab({ projects: [{ runsCount: 0 }], sharedHasContent: true }), false);
});

test('shouldShowCompareTab: projects without a runsCount field count as zero runs', () => {
  assert.equal(shouldShowCompareTab({ projects: [{}, {}], sharedHasContent: false }), false);
  assert.equal(shouldShowCompareTab({ projects: [{}, { runsCount: 1 }], sharedHasContent: true }), true);
});

test('shouldShowCompareTab: a missing/undefined projects list is treated as empty', () => {
  assert.equal(shouldShowCompareTab({ sharedHasContent: false }), false);
});

// ---------------------------------------------------------------------------
// shouldRedirectToRemoteRepositories
// ---------------------------------------------------------------------------

test('shouldRedirectToRemoteRepositories: redirects only from the default overview landing with zero local projects', () => {
  const base = {
    projectsLoaded: true, projectsCount: 0, selectedSource: 'local',
    sharedSettled: true, sharedHasContent: true, activeTab: 'overview',
  };
  assert.equal(shouldRedirectToRemoteRepositories(base), true);
  assert.equal(shouldRedirectToRemoteRepositories({ ...base, activeTab: 'settings' }), false);
  assert.equal(shouldRedirectToRemoteRepositories({ ...base, projectsCount: 2 }), false);
  assert.equal(shouldRedirectToRemoteRepositories({ ...base, selectedSource: 'shared' }), false);
  assert.equal(shouldRedirectToRemoteRepositories({ ...base, sharedHasContent: false }), false);
});
