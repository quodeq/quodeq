import test from 'node:test';
import assert from 'node:assert/strict';
import {
  isEvaluatableSource, shouldShowEvaluate,
  resolveProjectDisplayName, shouldShowProjectTabs, selectSidebarCounts,
  shouldRedirectToRepositories, shouldShowCompareTab,
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
// shouldShowEvaluate: a selected local project that has landed. Both the
// TopBar button and the sidebar tab read it.
// ---------------------------------------------------------------------------

test('shouldShowEvaluate: a selected local project, and only then', () => {
  const info = { id: 'p1', path: '/u/repos/app', originUrl: 'https://github.com/acme/app.git' };
  assert.equal(shouldShowEvaluate({ selectedSource: 'local', selectedProjectInfo: info }), true);
  assert.equal(shouldShowEvaluate({ selectedSource: 'local', selectedProjectInfo: null }), false);
  assert.equal(shouldShowEvaluate({ selectedSource: 'shared', selectedProjectInfo: info }), false);
  assert.equal(shouldShowEvaluate({ selectedSource: undefined, selectedProjectInfo: info }), true);
});

test('shouldShowEvaluate: hidden while the selected project is the one still cloning', () => {
  const info = { id: 'p1', path: '/u/repos/app', originUrl: 'https://github.com/acme/app.git' };
  const cloning = { repo: 'https://github.com/acme/app', dest: '/tmp/repos/app' };
  assert.equal(shouldShowEvaluate({ selectedSource: 'local', selectedProjectInfo: info, cloneSlot: cloning }), false);
  const other = { repo: 'https://github.com/acme/other.git', dest: '/u/repos/other' };
  assert.equal(shouldShowEvaluate({ selectedSource: 'local', selectedProjectInfo: info, cloneSlot: other }), true);
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

test('shouldShowProjectTabs: local gates on a selected project existing, runs or not', () => {
  assert.equal(shouldShowProjectTabs({ selectedSource: 'local', selectedProjectInfo: { id: 'p1', runsCount: 3 } }), true);
  assert.equal(shouldShowProjectTabs({ selectedSource: 'local', selectedProjectInfo: { id: 'p1', runsCount: 0 } }), true);
  assert.equal(shouldShowProjectTabs({ selectedSource: 'local', selectedProjectInfo: null }), false);
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
    filteredAccumulated: { summary: { totalViolations: 12, severity: { critical: 1, major: 4, minor: 7 } } },
    accumulated: { summary: { totalViolations: 9, severity: { critical: 0, major: 9, minor: 0 } } },
    filteredTrend: [1, 2],
    dashboard: { trend: [1, 2, 3] },
  });
  assert.deepEqual(counts, { violationsCount: 5, historyCount: 2 });
});

test('selectSidebarCounts: zero majors shows 0, not the total and not null', () => {
  const counts = selectSidebarCounts({
    filteredAccumulated: { summary: { totalViolations: 9, severity: { critical: 0, major: 0, minor: 9 } } },
    accumulated: null, filteredTrend: [], dashboard: null,
  });
  assert.equal(counts.violationsCount, 0);
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

test('shouldShowCompareTab: a single published project with no local runs is not enough', () => {
  assert.equal(shouldShowCompareTab({ projects: [], sharedHasContent: true, sharedPublishedCount: 1 }), false);
  assert.equal(shouldShowCompareTab({ projects: [{ runsCount: 0 }], sharedHasContent: true }), false);
});

test('shouldShowCompareTab: two published projects are enough with zero local projects', () => {
  assert.equal(shouldShowCompareTab({ projects: [], sharedHasContent: true, sharedPublishedCount: 2 }), true);
  assert.equal(shouldShowCompareTab({ projects: [{ runsCount: 0 }], sharedHasContent: true, sharedPublishedCount: 5 }), true);
});

test('shouldShowCompareTab: one local project with runs plus one published project is enough', () => {
  assert.equal(shouldShowCompareTab({ projects: [{ runsCount: 1 }], sharedHasContent: true, sharedPublishedCount: 1 }), true);
});

test('shouldShowCompareTab: projects without a runsCount field count as zero runs', () => {
  assert.equal(shouldShowCompareTab({ projects: [{}, {}], sharedHasContent: false }), false);
  assert.equal(shouldShowCompareTab({ projects: [{}, { runsCount: 1 }], sharedHasContent: true }), true);
});

test('shouldShowCompareTab: a missing/undefined projects list is treated as empty', () => {
  assert.equal(shouldShowCompareTab({ sharedHasContent: false }), false);
});

// ---------------------------------------------------------------------------
// shouldRedirectToRepositories
// ---------------------------------------------------------------------------

test('shouldRedirectToRepositories: redirects only from the default overview landing with zero local projects', () => {
  const base = { projectsLoaded: true, projectsCount: 0, selectedSource: 'local', activeTab: 'overview' };
  assert.equal(shouldRedirectToRepositories(base), true);
  assert.equal(shouldRedirectToRepositories({ ...base, activeTab: 'settings' }), false);
  assert.equal(shouldRedirectToRepositories({ ...base, projectsCount: 2 }), false);
  assert.equal(shouldRedirectToRepositories({ ...base, selectedSource: 'shared' }), false);
  assert.equal(shouldRedirectToRepositories({ ...base, projectsLoaded: false }), false);
});
