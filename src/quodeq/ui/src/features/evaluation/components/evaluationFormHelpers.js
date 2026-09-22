/**
 * Pure payload-building helper for EvaluationForm.
 *
 * Split out of EvaluationForm.jsx verbatim; re-exported from there so
 * `from './EvaluationForm.jsx'` importers (including the test) keep
 * working unchanged.
 */
import { CLEAN_PERSIST } from './scanModes.js';

export function buildEvaluationPayload({ repo, selectedDims, branch, scopePath, cleanScan }) {
  const payload = { repo };
  if (selectedDims.size > 0) payload.dimensions = [...selectedDims];
  if (branch) payload.branch = branch;
  if (scopePath) payload.scopePath = scopePath;
  payload.cleanScan = cleanScan !== CLEAN_PERSIST.OFF;
  return payload;
}
