import { STORAGE_KEY as POWER_KEY } from '../features/evaluation/components/powerLevels.js';
import { PROVIDER_SETTING_KEY } from '../constants.js';

const TIER_NAMES = ['fast', 'balanced', 'thorough'];
const DEFAULT_ANALYSIS_POWER = 2;

/**
 * useEvaluationLifecycle.js's storage-read/write and subagent-model-
 * resolution helpers. Extracted verbatim.
 */

// Every storage read below degrades the same way when the store throws. A
// function (not a shared string constant) so the literal stays a direct
// console.warn() argument -- lint:strings' dev-channel exemption only
// recognises that shape, not a literal read from a variable.
function warnStorageUnavailable(e) {
  console.warn('localStorage unavailable:', e);
}

/**
 * Storage reads degrade to '' when the backing store throws (private
 * mode, disabled storage) instead of crashing the caller, matching the
 * guarded reads below.
 */
export function safeGetItem(storage, key) {
  try { return storage.getItem(key) || ''; } catch (e) { warnStorageUnavailable(e); return ''; }
}

/**
 * The stored analysis power tier, falling back to DEFAULT_ANALYSIS_POWER when
 * nothing is stored or the store throws.
 */
export function readAnalysisPower(storage) {
  try { return Number(storage.getItem(POWER_KEY)) || DEFAULT_ANALYSIS_POWER; } catch (e) { warnStorageUnavailable(e); return DEFAULT_ANALYSIS_POWER; }
}

/**
 * Persists the analysis power tier, swallowing storage failures — the setting
 * is a preference, not something worth failing a run over.
 */
export function writeAnalysisPower(storage, level) {
  try { storage.setItem(POWER_KEY, String(level)); } catch (e) { warnStorageUnavailable(e); }
}

/**
 * Ollama uses a single analysis model; CLI providers use tier-based selection.
 * Falls back to the orchestrator model if no analysis-specific model is set.
 */
export function resolveSubagentModel({ get, analysisPower }) {
  const analysisModel = get(PROVIDER_SETTING_KEY.MODEL_ANALYSIS);
  if (analysisModel) return analysisModel;
  return get(`model-${TIER_NAMES[analysisPower - 1]}`) || get(PROVIDER_SETTING_KEY.MODEL) || undefined;
}

export { DEFAULT_ANALYSIS_POWER };
