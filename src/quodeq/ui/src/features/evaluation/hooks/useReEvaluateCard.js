/**
 * useReEvaluateCard — composes useReEvalInfo + useDimensionSelection plus
 * the scan-scope/estimate/budget state ReEvaluateCard needs.
 *
 * Split out of ReEvaluateCard.jsx verbatim.
 */
import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { usePluginDimensions } from './usePluginDimensions.js';
import { useScanData } from './useScanData.js';
import { useScanEstimates } from './useScanEstimates.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { ACTIVE_PROVIDER_KEY } from '../../../constants.js';
import { resolveProviderSettings } from '../../../utils/effectiveProviderSettings.js';
import { useReEvalInfo } from './useReEvalInfo.js';
import { useDimensionSelection } from './useDimensionSelection.js';

// The chips pre-select from the same resolution the start payload and the
// Settings screen use, so the form can never claim a budget the run
// wouldn't get if the user changed nothing.
function initialBudgetSeconds(storage = localStorage) {
  const provider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  if (!provider) return 0;
  return resolveProviderSettings(provider, storage).timeLimitS;
}

export function useReEvaluateCard(project, onStart, projectInfo, preselectDims) {
  const api = useApi();
  const { getProjectInfo, relocateProject } = api;
  const { info, error, retry, urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore } = useReEvalInfo(project, projectInfo, { getProjectInfo, relocateProject });
  const { allDimensions } = usePluginDimensions();
  const { showToast } = useSidePane();
  const [branch, setBranch] = useState(null);
  const [scopePath, setScopePath] = useState(null);
  const [timeLimitS, setTimeLimitS] = useState(() => initialBudgetSeconds());

  useEffect(() => { setScopePath(null); setBranch(null); }, [project]);

  const isLocal = info?.location === 'local';
  const { scanData } = useScanData(isLocal ? project : null);
  const { estimates, loading: estimatesLoading } = useScanEstimates(project, isLocal && !info?.pathMissing);

  const { selectedDims, toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan } =
    useDimensionSelection(allDimensions, info, branch, scopePath, onStart, showToast, preselectDims, project, timeLimitS);

  return {
    info, error, retry, allDimensions, selectedDims,
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
    isLocal, scanData, estimates, estimatesLoading, branch, setBranch, scopePath, setScopePath,
    timeLimitS, setTimeLimitS,
  };
}
