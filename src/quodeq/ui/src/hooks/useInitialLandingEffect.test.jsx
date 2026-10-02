import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useInitialLandingEffect } from './useAppEffects.js';
import { NAV_TAB } from '../vocab/navTab.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';

// The landing redirect is derived, not latched: it re-runs whenever the
// project list or the shared signal changes, so shared content that arrives
// mid-session (a connect from Settings, a first sync) moves the user off the
// empty "no projects" Overview without a reload. It only ever moves a user
// who is still on that landing.

const NOTHING = { settled: true, hasContent: false };
const SHARED_CONTENT = { settled: true, hasContent: true };

function props({ projects = [], projectsLoaded = true, selectedSource = PROJECT_SOURCE.LOCAL, sharedSignal = NOTHING, activeTab = NAV_TAB.OVERVIEW, navTab }) {
  return {
    state: { projectsLoaded, projects, selectedSource, activePage: { page: activeTab } },
    sharedSignal,
    activeTab,
    navTab,
  };
}

function renderLanding(initial) {
  const navTab = vi.fn();
  const utils = renderHook((p) => useInitialLandingEffect(p), { initialProps: props({ ...initial, navTab }) });
  const update = (next) => utils.rerender(props({ ...initial, ...next, navTab }));
  return { ...utils, navTab, update };
}

describe('useInitialLandingEffect (derived landing)', () => {
  it('stays on the landing while there is nothing to show', () => {
    const { navTab } = renderLanding({});
    expect(navTab).not.toHaveBeenCalled();
  });

  it('re-runs when shared content appears and moves the landing to the projects list', () => {
    const { navTab, update } = renderLanding({});
    expect(navTab).not.toHaveBeenCalled();
    update({ sharedSignal: SHARED_CONTENT });
    expect(navTab).toHaveBeenCalledWith(NAV_TAB.PROJECTS);
  });

  it('waits for both the project list and the shared signal before deciding', () => {
    const { navTab, update } = renderLanding({ projectsLoaded: false, sharedSignal: { settled: false, hasContent: false } });
    update({ projectsLoaded: true, sharedSignal: { settled: false, hasContent: true } });
    expect(navTab).not.toHaveBeenCalled();
    update({ projectsLoaded: true, sharedSignal: SHARED_CONTENT });
    expect(navTab).toHaveBeenCalledWith(NAV_TAB.PROJECTS);
  });

  it('never moves a user off a page they chose', () => {
    const { navTab, update } = renderLanding({ activeTab: NAV_TAB.SETTINGS });
    update({ sharedSignal: SHARED_CONTENT });
    expect(navTab).not.toHaveBeenCalled();
  });

  it('does not redirect when local projects exist', () => {
    const { navTab, update } = renderLanding({ projects: [{ id: 'a' }] });
    update({ sharedSignal: SHARED_CONTENT });
    expect(navTab).not.toHaveBeenCalled();
  });

  it('does not redirect a restored shared selection', () => {
    const { navTab, update } = renderLanding({ selectedSource: PROJECT_SOURCE.SHARED });
    update({ sharedSignal: SHARED_CONTENT });
    expect(navTab).not.toHaveBeenCalled();
  });

  it('a tab change alone does not re-run it: going back to Overview by choice is respected', () => {
    const { navTab, update } = renderLanding({ sharedSignal: SHARED_CONTENT, activeTab: NAV_TAB.SETTINGS });
    update({ sharedSignal: SHARED_CONTENT, activeTab: NAV_TAB.OVERVIEW });
    expect(navTab).not.toHaveBeenCalled();
  });
});
