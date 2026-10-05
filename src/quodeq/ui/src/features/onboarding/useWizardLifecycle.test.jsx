import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { withQueryClient } from '../../test-utils/withQueryClient.jsx';
import { useWizardLifecycle } from './useWizardLifecycle.js';
import { SKIPPED_KEY, SKIPPED_VALUE, STEP_WELCOME, STEP_ANALYZE } from './wizardSteps.js';
import { PROJECT_SOURCE } from '../../vocab/projectSource.js';
import { NAV_TAB } from '../../vocab/navTab.js';
import { WIZARD_SOURCE } from './onboardingVocab.js';

// The auto-open is derived from its inputs rather than decided once: it is
// re-evaluated whenever the project list or the shared signal changes, never
// opens while either is still resolving or once the user opted out, and a
// welcome-step wizard steps aside on its own when shared content shows up
// (a team repo connected mid-session gives the user something to look at).

const NOTHING = { settled: true, hasContent: false };
const UNSETTLED = { settled: false, hasContent: false };
const SHARED_CONTENT = { settled: true, hasContent: true };

function props({ projects = [], projectsLoaded = true, sharedSignal = NOTHING, isEvaluating = false }) {
  return {
    state: { projectsLoaded, projects, selectedSource: PROJECT_SOURCE.LOCAL, liveEvaluation: { actions: { startEvaluation: vi.fn() } } },
    navTab: vi.fn(),
    isEvaluating,
    sharedSignal,
  };
}

function renderLifecycle(initial = {}) {
  const utils = renderHook((p) => useWizardLifecycle(p), { initialProps: props(initial), wrapper: withQueryClient() });
  const update = (next) => utils.rerender(props({ ...initial, ...next }));
  return { ...utils, update };
}

beforeEach(() => { localStorage.clear(); });

describe('useWizardLifecycle auto-open (derived)', () => {
  it('opens on the welcome step for a fresh install with nothing to show', () => {
    const { result } = renderLifecycle();
    expect(result.current.wizardEntry).toEqual({ startStep: STEP_WELCOME, isFirstProject: true, source: WIZARD_SOURCE.FIRST_RUN });
  });

  it('does not open while the project list or the shared signal is still resolving', () => {
    const { result, update } = renderLifecycle({ projectsLoaded: false, sharedSignal: UNSETTLED });
    expect(result.current.wizardEntry).toBeNull();
    update({ projectsLoaded: true, sharedSignal: UNSETTLED });
    expect(result.current.wizardEntry).toBeNull();
    update({ projectsLoaded: true, sharedSignal: NOTHING });
    expect(result.current.wizardEntry).not.toBeNull();
  });

  it('does not open when shared content arrives before the decision settles', () => {
    const { result, update } = renderLifecycle({ sharedSignal: UNSETTLED });
    update({ sharedSignal: SHARED_CONTENT });
    expect(result.current.wizardEntry).toBeNull();
  });

  it('never opens when the user opted out', () => {
    localStorage.setItem(SKIPPED_KEY, SKIPPED_VALUE);
    const { result } = renderLifecycle();
    expect(result.current.wizardEntry).toBeNull();
  });

  it('closes itself when shared content appears while it sits on the welcome step', () => {
    const { result, update } = renderLifecycle();
    expect(result.current.wizardEntry).not.toBeNull();
    update({ sharedSignal: SHARED_CONTENT });
    expect(result.current.wizardEntry).toBeNull();
  });

  it('a manually opened welcome wizard is not closed by shared content', () => {
    const { result, update } = renderLifecycle({ projects: [{ id: 'a' }] });
    act(() => { result.current.setWizardEntry({ startStep: STEP_WELCOME }); });
    act(() => { result.current.wizardHandlers.onStepChange(STEP_WELCOME); });
    update({ projects: [{ id: 'a' }, { id: 'pulled' }] });
    update({ projects: [{ id: 'a' }, { id: 'pulled' }], sharedSignal: SHARED_CONTENT });
    expect(result.current.wizardEntry).toEqual({ startStep: STEP_WELCOME });
  });

  it('does not reopen after an auto-close when the content disappears again', () => {
    const { result, update } = renderLifecycle();
    update({ sharedSignal: SHARED_CONTENT });
    expect(result.current.wizardEntry).toBeNull();
    update({ sharedSignal: NOTHING });
    expect(result.current.wizardEntry).toBeNull();
  });

  it('closes itself when local projects arrive (a pull or import) while it sits on the welcome step', () => {
    const { result, update } = renderLifecycle();
    update({ projects: [{ id: 'pulled' }] });
    expect(result.current.wizardEntry).toBeNull();
  });

  it('stays open once the user has moved past the welcome step', () => {
    const { result, update } = renderLifecycle();
    act(() => { result.current.wizardHandlers.onStepChange(STEP_ANALYZE); });
    update({ sharedSignal: SHARED_CONTENT });
    expect(result.current.wizardEntry).not.toBeNull();
  });

  it('does not reopen after the user closed it, whatever the inputs do next', () => {
    const { result, update } = renderLifecycle();
    act(() => { result.current.wizardHandlers.onClose({ saved: false }); });
    expect(result.current.wizardEntry).toBeNull();
    update({ sharedSignal: UNSETTLED });
    update({ sharedSignal: NOTHING });
    expect(result.current.wizardEntry).toBeNull();
  });

  it('does not open for a user who already had local projects this session', () => {
    const { result, update } = renderLifecycle({ projects: [{ id: 'a' }] });
    update({ projects: [] });
    expect(result.current.wizardEntry).toBeNull();
  });

  it('defers while an evaluation runs and opens once it ends with still nothing to show', () => {
    const { result, update } = renderLifecycle({ isEvaluating: true });
    expect(result.current.wizardEntry).toBeNull();
    update({ isEvaluating: false });
    expect(result.current.wizardEntry).not.toBeNull();
  });

  it('a welcome opened from add project is not closed by shared content', () => {
    const { result, update } = renderLifecycle();
    act(() => { result.current.wizardHandlers.onClose({ saved: false }); });
    const entry = { startStep: STEP_WELCOME, isFirstProject: true, source: WIZARD_SOURCE.ADD };
    act(() => { result.current.setWizardEntry(entry); });
    act(() => { result.current.wizardHandlers.onStepChange(STEP_WELCOME); });
    update({ sharedSignal: SHARED_CONTENT });
    expect(result.current.wizardEntry).toBe(entry);
  });
});

describe('useWizardLifecycle welcome exits', () => {
  it('closing a welcome opened from Settings never writes the skip flag', () => {
    const { result } = renderLifecycle({ projects: [{ id: 'a' }] });
    act(() => { result.current.setWizardEntry({ startStep: STEP_WELCOME, isFirstProject: false, source: WIZARD_SOURCE.SETTINGS }); });
    act(() => { result.current.wizardHandlers.onClose({ saved: false }); });
    expect(result.current.wizardEntry).toBeNull();
    expect(localStorage.getItem(SKIPPED_KEY)).toBeNull();
  });

  it('an add that started a clone closes the wizard onto the repositories tab, with nothing to select yet', () => {
    const p = props({});
    p.state.handleProjectChange = vi.fn();
    const { result } = renderHook((q) => useWizardLifecycle(q), { initialProps: p, wrapper: withQueryClient() });
    act(() => { result.current.wizardHandlers.onClose({ saved: true, projectId: null, cloning: true }); });
    expect(result.current.wizardEntry).toBeNull();
    expect(p.navTab).toHaveBeenCalledWith(NAV_TAB.PROJECTS);
    expect(p.state.handleProjectChange).not.toHaveBeenCalled();
  });

  it('an add that registered a folder lands on the repositories tab with the project selected', () => {
    const p = props({ projects: [{ id: 'a' }] });
    p.state.handleProjectChange = vi.fn();
    p.state.selectedProject = 'a';
    const { result } = renderHook((q) => useWizardLifecycle(q), { initialProps: p, wrapper: withQueryClient() });
    act(() => { result.current.setWizardEntry({ startStep: STEP_ANALYZE, isFirstProject: false, source: WIZARD_SOURCE.ADD }); });
    act(() => { result.current.wizardHandlers.onClose({ saved: true, projectId: 'p-new', cloning: false }); });
    expect(p.navTab).toHaveBeenCalledWith(NAV_TAB.PROJECTS);
    expect(p.state.handleProjectChange).toHaveBeenCalledWith('p-new', PROJECT_SOURCE.LOCAL);
  });

  it('go to repositories closes the wizard and opens the repositories tab', () => {
    const p = props({});
    const { result } = renderHook((q) => useWizardLifecycle(q), { initialProps: p, wrapper: withQueryClient() });
    expect(result.current.wizardEntry).not.toBeNull();
    act(() => { result.current.wizardHandlers.onGoToRepositories(); });
    expect(result.current.wizardEntry).toBeNull();
    expect(p.navTab).toHaveBeenCalledWith(NAV_TAB.PROJECTS);
  });
});
