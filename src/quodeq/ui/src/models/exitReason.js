/**
 * Exit-reason display map — turns machine exit codes from the backend
 * (status.json `exit_reason`, dimensions.json `exit_reason`/`reason`) into
 * a short human label plus, where the user can actually do something, an
 * actionable hint.
 *
 * Unknown codes fall back to the raw code so new backend reasons degrade
 * to the old verbatim behaviour instead of hiding information.
 */
import { t } from '../strings/index.js';

// Not an error: hitting the time budget is the user's own setting doing its
// job. The hint just says what happens to the remainder.
const TIME_LIMIT = {
  label: t('exitReason.timeLimitLabel'),
  hint: t('exitReason.timeLimitHint'),
};

const FAILURE_STREAK = {
  label: t('exitReason.failureStreakLabel'),
  hint: t('exitReason.failureStreakHint'),
  // A run can finish `done` with this reason when the provider died after
  // partial progress; the UI should then warn that results are incomplete.
  warn: true,
};

const CANCELLED = { label: t('exitReason.cancelledLabel'), hint: null };

export const EXIT_REASON_INFO = {
  provider_fatal: {
    label: t('exitReason.providerFatalLabel'),
    hint: t('exitReason.providerFatalHint'),
    warn: true,
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
  // hasOwn, not a plain lookup: exit_reason comes off the backend payload,
  // and EXIT_REASON_INFO['constructor'] would return an inherited function
  // rather than the null this contract promises for unknown codes.
  return Object.hasOwn(EXIT_REASON_INFO, code) ? EXIT_REASON_INFO[code] : null;
}

/** Human label for a code; unknown codes pass through verbatim. */
export function exitReasonLabel(code) {
  return exitReasonInfo(code)?.label ?? code;
}

/** Actionable hint for a code, or null when there is nothing to suggest. */
export function exitReasonHint(code) {
  return exitReasonInfo(code)?.hint ?? null;
}

/**
 * True when a run that finished `done` with this reason should still show a
 * "stopped early, results are partial" warning (provider died mid-run).
 */
export function exitReasonWarn(code) {
  return exitReasonInfo(code)?.warn === true;
}

/**
 * True when the run ended because it hit its time budget. Not an error:
 * the user's own limit doing its job, so callers should render it with
 * neutral styling instead of failure styling.
 */
export function isTimeLimitExit(code) {
  return code === 'deadline' || code === 'time_limit';
}
