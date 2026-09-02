import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {
  buildEvalPrincipal, ROUTE_RENDERERS, isSharedSource, shouldBounceToEvaluate, shouldShowEvaluateButton,
  resolveSelectionAfterSharedDisconnect, shouldAutoOpenOnboardingWizard, shouldRedirectToRemoteRepositories, shouldShowProjectTabs,
  buildNavigationBundle, buildDashboardDataBundle, shouldWallEmptyProjects, buildWizardHandlers, buildAssistantSessionPayload,
  buildAssistantActionAppliedHandler, resolveProjectDisplayName, selectSidebarCounts,
  shouldShowStartupLoader,
} from './App.jsx';
import Sidebar from './components/Sidebar.jsx';

// Split from App.test.jsx: shouldAutoOpenOnboardingWizard,
// shouldRedirectToRemoteRepositories, shouldShowProjectTabs,
// selectSidebarCounts, and the Sidebar shared-selection tabs component test.

// Important 3: the onboarding wizard must not auto-open over a teammate's
// working shared-project view just because state.projects (the LOCAL list)
// is empty.
describe('shouldAutoOpenOnboardingWizard', () => {
  const base = { projectsLoaded: true, projectsCount: 0, selectedSource: 'local', isEvaluating: false };

  it('opens for a fresh local install (no projects, local source, not evaluating)', () => {
    expect(shouldAutoOpenOnboardingWizard(base)).toBe(true);
  });

  it('does not open for a shared selection even with zero local projects', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, selectedSource: 'shared' })).toBe(false);
  });

  it('does not open before projects have loaded', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, projectsLoaded: false })).toBe(false);
  });

  it('does not open once local projects exist', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, projectsCount: 3 })).toBe(false);
  });

  it('does not open while an evaluation is running', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, isEvaluating: true })).toBe(false);
  });

  // Remote-content awareness: a configured shared repo with published
  // projects is a working view the user can browse — the wizard must not
  // open over it (spec 2026-07-23-remote-repos-without-local-projects).
  it('defers (no open) while the shared-repo signal has not settled', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, sharedSettled: false })).toBe(false);
  });

  it('does not open when the shared repo has content', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, sharedSettled: true, sharedHasContent: true })).toBe(false);
  });

  it('opens when the shared repo settled without content', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, sharedSettled: true, sharedHasContent: false })).toBe(true);
  });
});

// One-shot landing decision: a fresh start with zero local projects but
// remote content lands on the repositories tab instead of the dead-end
// 'overview' empty state. Latched in App once inputs settle — these tests
// pin the pure decision only.
describe('shouldRedirectToRemoteRepositories', () => {
  const base = {
    projectsLoaded: true, projectsCount: 0, selectedSource: 'local',
    sharedSettled: true, sharedHasContent: true, activeTab: 'overview',
  };

  it('redirects a fresh start: zero local projects, remote content, default overview landing', () => {
    expect(shouldRedirectToRemoteRepositories(base)).toBe(true);
  });

  it('does not redirect before local projects load', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, projectsLoaded: false })).toBe(false);
  });

  it('does not redirect before the shared signal settles', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, sharedSettled: false })).toBe(false);
  });

  it('does not redirect when local projects exist', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, projectsCount: 2 })).toBe(false);
  });

  it('does not redirect over a restored shared selection (already a working view)', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, selectedSource: 'shared' })).toBe(false);
  });

  it('does not redirect without remote content', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, sharedHasContent: false })).toBe(false);
  });

  it('does not redirect off a non-default tab the user already navigated to', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, activeTab: 'settings' })).toBe(false);
  });
});

// Sidebar tab gating must be source-aware. hasCurrentProjectRuns is derived
// from the LOCAL project list, so a shared selection with no local mirror
// resolves to null info / zero runs and the four project-data tabs vanish
// even though every one of those pages works for shared projects. The shared
// signal is the resolved sharedProjectInfo (already fetched at App level by
// useDashboard): the shared info payload carries no runsCount at all, and a
// project only appears in the shared repo once published with runs, so
// presence of its info is the correct "has data to show" signal.
describe('shouldShowProjectTabs', () => {
  it('shows tabs for a local project with runs', () => {
    expect(shouldShowProjectTabs({
      selectedSource: 'local', hasCurrentProjectRuns: true, sharedProjectInfo: null,
    })).toBe(true);
  });

  it('hides tabs for a local project with zero runs', () => {
    expect(shouldShowProjectTabs({
      selectedSource: 'local', hasCurrentProjectRuns: false, sharedProjectInfo: null,
    })).toBe(false);
  });

  it('shows tabs for a shared selection once its shared info has resolved, ignoring the local run count', () => {
    expect(shouldShowProjectTabs({
      selectedSource: 'shared',
      hasCurrentProjectRuns: false, // no local mirror -> the local signal reads empty
      sharedProjectInfo: { id: 'team-proj', name: 'team-proj' },
    })).toBe(true);
  });

  it('hides tabs for a shared selection while its shared info has not resolved', () => {
    expect(shouldShowProjectTabs({
      selectedSource: 'shared', hasCurrentProjectRuns: false, sharedProjectInfo: null,
    })).toBe(false);
  });

  it('ignores a colliding local twin\'s shared info for a local selection', () => {
    // A shared project's id can collide with a local one by design. When the
    // LOCAL twin is selected, the gate must read the local run count, not the
    // leftover shared info object.
    expect(shouldShowProjectTabs({
      selectedSource: 'local', hasCurrentProjectRuns: false, sharedProjectInfo: { id: 'team-proj' },
    })).toBe(false);
  });
});

// Scenario 7 (collision): the sidebar's violations/history badges must not
// keep showing the OUTGOING project's numbers once a project switch is in
// flight. `accumulated`/`dashboard` already reset to null the instant
// `selectedProject` changes (samePlaceholderScope, api/queryKeys.js), so
// reading straight off them here is what clears the badges immediately
// instead of holding onto stale numbers until the new project's fetch lands.
describe('selectSidebarCounts', () => {
  it('reads violations/history counts off the filtered view when present', () => {
    const result = selectSidebarCounts({
      filteredAccumulated: { summary: { totalViolations: 12 } },
      accumulated: { summary: { totalViolations: 99 } },
      filteredTrend: [{ runId: 'r1' }, { runId: 'r2' }],
      dashboard: { trend: [{ runId: 'r1' }] },
    });
    expect(result.violationsCount).toBe(12);
    expect(result.historyCount).toBe(2);
  });

  it('falls back to the unfiltered accumulated/dashboard when the filtered view has nothing', () => {
    const result = selectSidebarCounts({
      filteredAccumulated: null,
      accumulated: { summary: { totalViolations: 7 } },
      filteredTrend: [],
      dashboard: { trend: [{ runId: 'r1' }, { runId: 'r2' }] },
    });
    expect(result.violationsCount).toBe(7);
    expect(result.historyCount).toBe(2);
  });

  it('clears both counts on a project switch, before the new project data lands', () => {
    const result = selectSidebarCounts({
      filteredAccumulated: null,
      accumulated: null,
      filteredTrend: [],
      dashboard: null,
    });
    expect(result.violationsCount).toBeNull();
    expect(result.historyCount).toBeNull();
  });
});

describe('Sidebar project-data tabs for a shared-only selection (component)', () => {
  const DATA_TABS = ['overview', 'violations', 'map', 'history'];

  it('renders all four data tabs when the shared project info has resolved', () => {
    const show = shouldShowProjectTabs({
      selectedSource: 'shared',
      hasCurrentProjectRuns: false, // shared-only: no local mirror
      sharedProjectInfo: { id: 'team-proj', name: 'team-proj' },
    });
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} selectedSource="shared" showProjectTabs={show} />);
    for (const tab of DATA_TABS) {
      expect(screen.getByTitle(tab)).toBeInTheDocument();
    }
  });

  it('hides the data tabs while the shared info is still loading', () => {
    const show = shouldShowProjectTabs({
      selectedSource: 'shared', hasCurrentProjectRuns: false, sharedProjectInfo: null,
    });
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} selectedSource="shared" showProjectTabs={show} />);
    for (const tab of DATA_TABS) {
      expect(screen.queryByTitle(tab)).toBeNull();
    }
  });
});
