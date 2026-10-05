import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useInitialLandingEffect } from './useAppEffects.js';
import { NAV_TAB } from '../vocab/navTab.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';

// The landing redirect is derived, not latched: it re-runs whenever the
// project list changes (load settling, the last project deleted), so an
// empty "no projects" Overview moves to the Repositories tab, the only tab
// that does anything without a project. It only ever moves a user who is
// still on that landing.

function props({ projects = [], projectsLoaded = true, selectedSource = PROJECT_SOURCE.LOCAL, activeTab = NAV_TAB.OVERVIEW, navTab }) {
  return {
    state: { projectsLoaded, projects, selectedSource, activePage: { page: activeTab } },
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
  it('a first start with no projects lands on the repositories tab', () => {
    const { navTab } = renderLanding({});
    expect(navTab).toHaveBeenCalledWith(NAV_TAB.PROJECTS);
  });

  it('waits for the project list before deciding', () => {
    const { navTab, update } = renderLanding({ projectsLoaded: false });
    expect(navTab).not.toHaveBeenCalled();
    update({ projectsLoaded: true });
    expect(navTab).toHaveBeenCalledWith(NAV_TAB.PROJECTS);
  });

  it('re-runs when the last project goes and the user sits on the empty landing', () => {
    const { navTab, update } = renderLanding({ projects: [{ id: 'a' }] });
    expect(navTab).not.toHaveBeenCalled();
    update({ projects: [] });
    expect(navTab).toHaveBeenCalledWith(NAV_TAB.PROJECTS);
  });

  it('never moves a user off a page they chose', () => {
    const { navTab, update } = renderLanding({ activeTab: NAV_TAB.SETTINGS });
    update({ projects: [] });
    expect(navTab).not.toHaveBeenCalled();
  });

  it('does not redirect when local projects exist', () => {
    const { navTab } = renderLanding({ projects: [{ id: 'a' }] });
    expect(navTab).not.toHaveBeenCalled();
  });

  it('does not redirect a restored shared selection', () => {
    const { navTab } = renderLanding({ selectedSource: PROJECT_SOURCE.SHARED });
    expect(navTab).not.toHaveBeenCalled();
  });

  it('a tab change alone does not re-run it: going back to Overview by choice is respected', () => {
    const { navTab, update } = renderLanding({ activeTab: NAV_TAB.SETTINGS });
    update({ activeTab: NAV_TAB.OVERVIEW });
    expect(navTab).not.toHaveBeenCalled();
  });
});
