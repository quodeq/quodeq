import { STORAGE_KEY as POWER_KEY } from '../features/evaluation/components/powerLevels.js';

const TIER_NAMES = ['fast', 'balanced', 'thorough'];
const DEFAULT_ANALYSIS_POWER = 2;

/**
 * useEvaluationLifecycle.js's storage-read/write and subagent-model-
 * resolution helpers. Extracted verbatim.
 */

// Storage reads degrade to '' when the backing store throws (private
// mode, disabled storage) instead of crashing the caller, matching the
// guarded reads below.
export function safeGetItem(storage, key) {
  try { return storage.getItem(key) || ''; } catch (e) { console.warn('localStorage unavailable:', e); return ''; }
}

export function readAnalysisPower(storage) {
  try { return Number(storage.getItem(POWER_KEY)) || DEFAULT_ANALYSIS_POWER; } catch (e) { console.warn('localStorage unavailable:', e); return DEFAULT_ANALYSIS_POWER; }
}

export function writeAnalysisPower(storage, level) {
  try { storage.setItem(POWER_KEY, String(level)); } catch (e) { console.warn('localStorage unavailable:', e); }
}

// Ollama uses a single analysis model; CLI providers use tier-based selection.
// Falls back to the orchestrator model if no analysis-specific model is set.
export function resolveSubagentModel({ get, analysisPower }) {
  const analysisModel = get('model-analysis');
  if (analysisModel) return analysisModel;
  return get(`model-${TIER_NAMES[analysisPower - 1]}`) || get('model') || undefined;
}

export { DEFAULT_ANALYSIS_POWER };
