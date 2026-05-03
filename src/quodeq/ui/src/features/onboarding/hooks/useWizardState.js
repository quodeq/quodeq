import { useReducer, useCallback } from 'react';

const DEFAULT_TIME_LIMIT_S = 600; // 10 minutes

function initialState(initial = {}) {
  return {
    step: initial.step || 'welcome',
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

function reducer(state, action) {
  switch (action.type) {
    case 'GO_TO_STEP':
      return { ...state, step: action.step };
    case 'SET_REPO':
      return { ...state, repo: { ...state.repo, ...action.repo } };
    case 'SCAN_START':
      return { ...state, repoScanSubState: 'scanning', scan: null, projectId: null };
    case 'SCAN_SUCCESS':
      return {
        ...state,
        repoScanSubState: 'scanned',
        scan: action.scan,
        projectId: action.projectId,
      };
    case 'SCAN_ERROR':
      return { ...state, repoScanSubState: 'error', scanError: action.error };
    case 'SCAN_RESET':
      return { ...state, repoScanSubState: 'idle', scan: null, projectId: null, scanError: null };
    case 'SET_PROVIDER':
      return { ...state, provider: { ...state.provider, ...action.provider } };
    case 'SET_PROVIDER_VIEW':
      return { ...state, providerView: action.view };
    case 'SET_TIME_LIMIT':
      return { ...state, totalTimeLimitS: action.seconds };
    case 'TOGGLE_STANDARD': {
      const next = new Set(state.standardIds);
      if (next.has(action.id)) next.delete(action.id);
      else next.add(action.id);
      // First-project: enforce single-select by clearing others before adding.
      if (state.isFirstProject && next.size > 1) {
        next.clear();
        next.add(action.id);
      }
      return { ...state, standardIds: next };
    }
    case 'LAUNCH_START':
      return { ...state, launching: true };
    case 'LAUNCH_ERROR':
      return { ...state, launching: false, launchError: action.error };
    case 'RESET':
      return initialState(action.initial);
    default:
      return state;
  }
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
