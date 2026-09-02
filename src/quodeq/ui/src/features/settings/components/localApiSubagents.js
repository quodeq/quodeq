import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';

// Local-API tabs default to a single subagent; clamp commits to [MIN, MAX]
// so an empty/garbage entry can't persist to storage. Was duplicated
// verbatim across OmlxTab/LlamaCppTab/OllamaTab before this extraction.
export const LOCAL_DEFAULT_SUBAGENTS = '1';
export function clampSubagents(raw) {
  const n = parseInt(raw, 10);
  if (Number.isNaN(n)) return LOCAL_DEFAULT_SUBAGENTS;
  return String(Math.max(MIN_SUBAGENTS, Math.min(MAX_SUBAGENTS, n)));
}
