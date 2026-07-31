/**
 * Exit-reason display map — turns machine exit codes from the backend
 * (status.json `exit_reason`, dimensions.json `exit_reason`/`reason`) into
 * a short human label plus, where the user can actually do something, an
 * actionable hint.
 *
 * Unknown codes fall back to the raw code so new backend reasons degrade
 * to the old verbatim behaviour instead of hiding information.
 */

const TIME_LIMIT = {
  label: 'time limit reached',
  hint: 'Raise the time limit or scan fewer dimensions to cover the remaining files.',
};

const FAILURE_STREAK = {
  label: 'repeated failures',
  hint: 'Stopped after consecutive agent failures. Check that the AI provider is running and reachable, then run again.',
};

const CANCELLED = { label: 'cancelled', hint: null };

export const EXIT_REASON_INFO = {
  provider_fatal: {
    label: 'AI provider error',
    hint: 'The AI provider rejected every request: quota exhausted, out of credits, or an invalid API key. Check your plan, billing or API key, then run again.',
  },
  failure_streak: FAILURE_STREAK,
  agent_failure_streak: FAILURE_STREAK,
  time_limit: TIME_LIMIT,
  deadline: TIME_LIMIT,
  cancelled: CANCELLED,
  cancelled_signal: CANCELLED,
};

/**
 * @param {string|null|undefined} code
 * @returns {{label: string, hint: string|null}|null} null for unknown/absent codes
 */
export function exitReasonInfo(code) {
  if (typeof code !== 'string') return null;
  return EXIT_REASON_INFO[code] ?? null;
}

/** Human label for a code; unknown codes pass through verbatim. */
export function exitReasonLabel(code) {
  return exitReasonInfo(code)?.label ?? code;
}

/** Actionable hint for a code, or null when there is nothing to suggest. */
export function exitReasonHint(code) {
  return exitReasonInfo(code)?.hint ?? null;
}
