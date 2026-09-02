import { pct } from './scanProgressTotals.js';
import { formatDuration } from '../../../utils/formatters.js';
import { exitReasonHint, exitReasonLabel } from '../../../models/exitReason.js';
import { t } from '../../../strings/index.js';

// Reasons surfaced as a badge so an unusually large estimate isn't a mystery.
export const ESTIMATE_REASON_LABEL = {
  'catching-up': t('evaluate.estimateCatchingUp'),
  'first-run': t('evaluate.estimateFirstRun'),
  'standards-changed': t('evaluate.estimateStandardsChanged'),
  'prompts-changed': t('evaluate.estimatePromptsChanged'),
};

function DimCount({ isPending, taken, total }) {
  if (isPending) {
    // Backend supplies accurate per-dim totals: a precomputed estimate for
    // pending dims, the live queue size for running/done. A 0 here means
    // estimates haven't landed yet — render nothing rather than a guess.
    return total > 0
      ? <span className="scan-progress__dim-meta-projected">{t('evaluate.countOf', { taken: 0, total })}</span>
      : <span className="scan-progress__dim-meta-projected">{t('evaluate.estimating')}</span>;
  }
  return <>{t('evaluate.countOf', { taken, total: total || '—' })}</>;
}

function DimMetaPending({ reasonBadge }) {
  return <span className="scan-progress__dim-meta-projected">{t('evaluate.queued')}{reasonBadge}</span>;
}

function DimMetaDone({ dim, taken, total }) {
  // Clamp adoption (sanctioned intended change): pct() caps at 100 where
  // the inline Math.round() above did not, so a done dim with taken>total
  // (count drift) no longer prints e.g. "105%". The null sentinel for a
  // zero total is preserved — it's load-bearing (chip renders only when
  // !== null).
  const coveragePct = total > 0 ? pct(taken, total) : null;
  const isPartial = typeof dim.exitReason === 'string' && dim.exitReason !== 'done';
  const hint = exitReasonHint(dim.exitReason);
  const partialTooltip = isPartial
    ? `${t('overview.stoppedReason', { reason: exitReasonLabel(dim.exitReason) })} · ${t('overview.filesOf', { read: taken, total })}${hint ? ` · ${hint}` : ''}`
    : undefined;
  return (
    <>
      {dim.violations > 0 && <><span className="scan-progress__v">{t('overview.violationsAbbrev', { count: dim.violations })}</span> · </>}
      {dim.compliance > 0 && <><span className="scan-progress__c">{t('evaluate.complianceAbbrev', { count: dim.compliance })}</span> · </>}
      {coveragePct !== null && (
        <><span
          className={`scan-progress__coverage${isPartial ? ' scan-progress__coverage--partial' : ''}`}
          title={partialTooltip}
        >{coveragePct}%</span>{dim.elapsedS != null && ' · '}</>
      )}
      {dim.elapsedS != null && formatDuration(dim.elapsedS)}
    </>
  );
}

function DimMetaRunning({ dim, reasonBadge }) {
  // Only show a clock segment when we actually have a number to print.
  // Without this guard, a running dim with no elapsed time yields a
  // dangling "· —" tail. The time budget is run-level (shared across
  // dimensions, shown in the footer), so rows only get their elapsed.
  const clockPart = dim.elapsedS != null
    ? <span className="scan-progress__budget">{formatDuration(dim.elapsedS)}</span>
    : null;
  return (
    <>
      {dim.activeAgents > 0 && <>{t('evaluate.agents', { count: dim.activeAgents })}</>}
      {reasonBadge}
      {dim.violations > 0 && <> · <span className="scan-progress__v">{t('overview.violationsAbbrev', { count: dim.violations })}</span></>}
      {dim.compliance > 0 && <> · <span className="scan-progress__c">{t('evaluate.complianceAbbrev', { count: dim.compliance })}</span></>}
      {clockPart && <> · {clockPart}</>}
    </>
  );
}

export default function DimRow({ dim }) {
  const taken = dim.files?.taken ?? 0;
  const isPending = dim.state === 'pending';
  const total = dim.files?.total ?? 0;
  const reasonLabel = ESTIMATE_REASON_LABEL[dim.estimateReason];
  const reasonBadge = reasonLabel
    ? <> · <span className="scan-progress__dim-reason">{reasonLabel}</span></>
    : null;
  // When the dimension reports `done`, force the bar to 100% even if
  // `files.taken < files.total` (incremental skips, dismissed files, etc.).
  // Backend `done` is the source of truth — count drift shouldn't make a
  // green dimension look red.
  const isDone = dim.state === 'done';
  const isRunning = dim.state === 'running';
  const p = isDone ? 100 : pct(taken, total);
  const dotClass = isDone ? ' scan-progress__dim-dot--done' : isRunning ? ' scan-progress__dim-dot--running' : '';
  const fillClass = isDone ? 'scan-progress__bar-fill--done' : '';

  const meta = isPending
    ? <DimMetaPending reasonBadge={reasonBadge} />
    : isDone
      ? <DimMetaDone dim={dim} taken={taken} total={total} />
      : <DimMetaRunning dim={dim} reasonBadge={reasonBadge} />;

  return (
    <div className={`scan-progress__dim${isPending ? ' scan-progress__dim--pending' : ''}`}>
      <span className="scan-progress__dim-lead">
        <span className={`scan-progress__dim-dot${dotClass}`} aria-hidden="true" />
        <span className="scan-progress__dim-name">{dim.id}</span>
      </span>
      <span className="scan-progress__dim-count"><DimCount isPending={isPending} taken={taken} total={total} /></span>
      <div className="scan-progress__bar scan-progress__bar--mini">
        <div className={`scan-progress__bar-fill ${fillClass}`} style={{ width: `${p}%` }} />
      </div>
      <span className="scan-progress__dim-meta">{meta}</span>
    </div>
  );
}
