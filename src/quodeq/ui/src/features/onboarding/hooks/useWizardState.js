import { useReducer, useCallback } from 'react';
import { STEP_WELCOME } from '../wizardSteps.js';

const DEFAULT_TIME_LIMIT_S = 600; // 10 minutes

function initialState(initial = {}) {
  return {
    step: initial.step || STEP_WELCOME,
    repoScanSubState: 'idle',
    repo: { source: 'url', value: '', branch: null, scopePath: null },
    projectId: null,
    scan: null,
    provider: { id: null, model: null, classification: null },
    providerView: 'pre-recommended',
    standardIds: new Set(),
    isFirstProject: initial.isFirstProject ?? true,
    totalTimeLimitS: DEFAULT_TIME_LIMIT_S,
    launching: false,
    ...initial,
  };
}

/**
 * Flip one standard on or off. A first project is single-select, so turning
 * one on there clears whatever else was picked.
 */
function toggleStandard(state, id) {
  const next = new Set(state.standardIds);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  if (state.isFirstProject && next.size > 1) {
    next.clear();
    next.add(id);
  }
  return next;
}

/** One handler per action type; anything unlisted leaves the state alone. */
const HANDLERS = {
  GO_TO_STEP: (state, action) => ({ ...state, step: action.step }),
  SET_REPO: (state, action) => ({ ...state, repo: { ...state.repo, ...action.repo } }),
  SCAN_START: (state) => ({ ...state, repoScanSubState: 'scanning', scan: null, projectId: null }),
  SCAN_SUCCESS: (state, action) => ({
    ...state,
    repoScanSubState: 'scanned',
    scan: action.scan,
    projectId: action.projectId,
  }),
  SCAN_ERROR: (state, action) => ({ ...state, repoScanSubState: 'error', scanError: action.error }),
  SCAN_RESET: (state) => ({ ...state, repoScanSubState: 'idle', scan: null, projectId: null, scanError: null }),
  SET_PROVIDER: (state, action) => ({ ...state, provider: { ...state.provider, ...action.provider } }),
  SET_PROVIDER_VIEW: (state, action) => ({ ...state, providerView: action.view }),
  SET_TIME_LIMIT: (state, action) => ({ ...state, totalTimeLimitS: action.seconds }),
  TOGGLE_STANDARD: (state, action) => ({ ...state, standardIds: toggleStandard(state, action.id) }),
  LAUNCH_START: (state) => ({ ...state, launching: true }),
  LAUNCH_ERROR: (state, action) => ({ ...state, launching: false, launchError: action.error }),
  RESET: (state, action) => initialState(action.initial),
};

function reducer(state, action) {
  const handler = HANDLERS[action.type];
  return handler ? handler(state, action) : state;
}

/**
 * Wizard state machine. Pass `initial` to seed step / isFirstProject when
 * opening the wizard at a non-default step.
 *
 * @param {{ initial?: object }} options
 */
export function useWizardState(options = {}) {
  const [state, dispatch] = useReducer(reducer, options.initial || {}, initialState);

  const goToStep = useCallback((step) => dispatch({ type: 'GO_TO_STEP', step }), []);
  const setRepo = useCallback((repo) => dispatch({ type: 'SET_REPO', repo }), []);
  const startScan = useCallback(() => dispatch({ type: 'SCAN_START' }), []);
  const succeedScan = useCallback(
    (projectId, scan) => dispatch({ type: 'SCAN_SUCCESS', projectId, scan }),
    [],
  );
  const failScan = useCallback((error) => dispatch({ type: 'SCAN_ERROR', error }), []);
  const resetScan = useCallback(() => dispatch({ type: 'SCAN_RESET' }), []);
  const setProvider = useCallback((provider) => dispatch({ type: 'SET_PROVIDER', provider }), []);
  const setProviderView = useCallback((view) => dispatch({ type: 'SET_PROVIDER_VIEW', view }), []);
  const setTimeLimit = useCallback((seconds) => dispatch({ type: 'SET_TIME_LIMIT', seconds }), []);
  const toggleStandard = useCallback((id) => dispatch({ type: 'TOGGLE_STANDARD', id }), []);
  const startLaunch = useCallback(() => dispatch({ type: 'LAUNCH_START' }), []);
  const failLaunch = useCallback((error) => dispatch({ type: 'LAUNCH_ERROR', error }), []);
  const reset = useCallback((initial) => dispatch({ type: 'RESET', initial }), []);

  return {
    state,
    goToStep,
    setRepo,
    startScan,
    succeedScan,
    failScan,
    resetScan,
    setProvider,
    setProviderView,
    setTimeLimit,
    toggleStandard,
    startLaunch,
    failLaunch,
    reset,
  };
}
