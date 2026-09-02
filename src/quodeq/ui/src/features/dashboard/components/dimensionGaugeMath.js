import { exitReasonLabel, exitReasonHint } from '../../../models/exitReason.js';
import { t, LOCALE } from '../../../strings/index.js';

/**
 * Build a coverage record for the gauge card's footer line.
 *
 * Every card with a date gets a footer line; `coveragePct` and `isPartial`
 * are derived from the same signals as the old partial badge:
 *   - "partial" when filesRead < sourceFileCount, OR
 *   - "partial" when exitReason is set to anything other than 'done'.
 * Legacy runs with neither signal end up complete-by-default.
 *
 * `coveragePct` is null when there are no file counts (legacy runs);
 * in that case the footer renders the date only.
 */
export function computeCoverageInfo(filesRead, sourceFileCount, exitReason) {
  const hasCounts =
    typeof filesRead === 'number' &&
    typeof sourceFileCount === 'number' &&
    sourceFileCount > 0;
  const coveragePct = hasCounts
    ? Math.round((filesRead / sourceFileCount) * 100)
    : null;
  const coverageIncomplete = hasCounts && filesRead < sourceFileCount;
  const exitIncomplete = typeof exitReason === 'string' && exitReason !== 'done';
  const isPartial = coverageIncomplete || exitIncomplete;
  return { filesRead, sourceFileCount, coveragePct, exitReason, isPartial };
}

export function buildPartialTooltip({ filesRead, sourceFileCount, exitReason }) {
  const hasCounts =
    typeof filesRead === 'number' &&
    typeof sourceFileCount === 'number' &&
    sourceFileCount > 0;
  const parts = [t('overview.partialRun')];
  if (hasCounts) {
    parts.push(t('overview.filesOf', { read: filesRead.toLocaleString(LOCALE), total: sourceFileCount.toLocaleString(LOCALE) }));
  }
  if (typeof exitReason === 'string') {
    parts.push(t('overview.stoppedReason', { reason: exitReasonLabel(exitReason) }));
    // A failure-streak (circuit-breaker) dimension is salvaged and shown with a
    // provisional score, but kept out of the overall grade. Say so explicitly.
    if (exitReason === 'failure_streak') {
      parts.push(t('overview.excludedFromGrade'));
    }
    const hint = exitReasonHint(exitReason);
    if (hint) parts.push(hint);
  }
  return parts.join(' · ');
}
