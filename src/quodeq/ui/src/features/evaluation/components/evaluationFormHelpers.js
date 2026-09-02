/**
 * Pure payload-building helper for EvaluationForm.
 *
 * Split out of EvaluationForm.jsx verbatim; re-exported from there so
 * `from './EvaluationForm.jsx'` importers (including the test) keep
 * working unchanged.
 */
export function buildEvaluationPayload({ repo, selectedDims, branch, scopePath, cleanScan }) {
  const payload = { repo };
  if (selectedDims.size > 0) payload.dimensions = [...selectedDims];
  if (branch) payload.branch = branch;
  if (scopePath) payload.scopePath = scopePath;
  payload.cleanScan = cleanScan !== 'off';
  return payload;
}
