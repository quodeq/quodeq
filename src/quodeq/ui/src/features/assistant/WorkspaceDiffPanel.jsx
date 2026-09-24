import { useMemo, useState } from 'react';
import { t } from '../../strings/index.js';
import { confirmDialog } from '../../utils/confirmDialog.js';
import { useWorkspaceDiff } from './hooks/useWorkspaceDiff.js';

export function classifyDiffLine(line) {
  if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff --git')) return 'wsdiff-file';
  if (line.startsWith('@@')) return 'wsdiff-hunk';
  if (line.startsWith('+')) return 'wsdiff-add';
  if (line.startsWith('-')) return 'wsdiff-del';
  return 'wsdiff-ctx';
}

// Diff lines mounted at once. The backend caps a diff at 2 MB of text but not
// by line count, so one diff can mean tens of thousands of spans. Past this
// the panel asks before mounting more. Not virtualized: what is shown stays
// one <pre>, so select, copy and find keep working.
export const DIFF_LINE_RENDER_CAP = 2000;

// Lines to show for this diff. The expansion is remembered per diff string,
// so a Refresh that brings a new diff starts from the cap again.
function useDiffLineWindow(diff) {
  const lines = useMemo(() => (diff === null ? [] : diff.split('\n')), [diff]);
  const [expanded, setExpanded] = useState({ diff: null, count: DIFF_LINE_RENDER_CAP });
  const limit = expanded.diff === diff ? expanded.count : DIFF_LINE_RENDER_CAP;
  const shownCount = Math.min(lines.length, limit);
  const rendered = useMemo(() => lines.slice(0, shownCount).map((line, i) => (
    // eslint-disable-next-line react/no-array-index-key
    <span key={i} className={classifyDiffLine(line)}>{line}{'\n'}</span>
  )), [lines, shownCount]);
  const showMore = () => setExpanded({ diff, count: shownCount + DIFF_LINE_RENDER_CAP });
  return { rendered, shownCount, totalCount: lines.length, showMore };
}

function WorkspaceDiffOutcome({ outcome }) {
  return (
    <div className="workspace-diff">
      <p className="workspace-diff-outcome" role="status" aria-live="polite">
        {outcome.kind === 'applied' && t('assistant.outcomeApplied')}
        {outcome.kind === 'discarded' && t('assistant.outcomeDiscarded')}
        {outcome.kind === 'pr' && (outcome.prUrl
          ? <>{t('assistant.prCreated')} <a href={outcome.prUrl} target="_blank" rel="noreferrer">{outcome.prUrl}</a></>
          : (outcome.message || t('assistant.outcomeBranchKept')))}
      </p>
    </div>
  );
}

function WorkspaceDiffBody({ diff, truncated, error, empty }) {
  const { rendered, shownCount, totalCount, showMore } = useDiffLineWindow(diff);
  const capped = shownCount < totalCount;

  return (
    <>
      {truncated && (
        <p className="workspace-diff-warning" role="alert">
          {t('assistant.diffTruncated')}
        </p>
      )}
      {error && <p className="workspace-diff-error" role="alert">{error}</p>}
      {diff === null && !error && <p aria-live="polite">{t('assistant.loadingDiff')}</p>}
      {empty && <p className="workspace-diff-empty">{t('assistant.noChanges')}</p>}
      {diff !== null && !empty && (
        <>
          {capped && (
            <p className="workspace-diff-warning">
              {t('assistant.diffShowingLines', { shown: shownCount, total: totalCount })}
            </p>
          )}
          <pre className="workspace-diff-body">{rendered}</pre>
          {capped && (
            <button type="button" onClick={showMore}>{t('assistant.diffShowMore')}</button>
          )}
        </>
      )}
    </>
  );
}

function WorkspaceDiffActions({ diff, empty, busy, prOpen, setPrOpen, prTitle, setPrTitle, prBody, setPrBody, loadDiff, applyToRepo, discard, createPr }) {
  return (
    <>
      <div className="workspace-diff-actions">
        <button type="button" disabled={busy} onClick={() => loadDiff()}>
          {t('assistant.refresh')}
        </button>
        <button type="button" disabled={busy || !diff || empty}
          onClick={() => applyToRepo()}>
          {t('assistant.applyToRepo')}
        </button>
        <button type="button" disabled={busy || !diff || empty}
          onClick={() => setPrOpen((v) => !v)} aria-expanded={prOpen}>
          {t('assistant.createPrEllipsis')}
        </button>
        <button type="button" disabled={busy}
          onClick={async () => {
            const ok = await confirmDialog({
              title: t('assistant.discardConfirmTitle'),
              message: t('assistant.discardConfirmMessage'),
              variant: 'danger',
            });
            if (!ok) return;
            discard();
          }}>
          {t('assistant.discard')}
        </button>
      </div>
      {prOpen && (
        <div className="workspace-diff-pr">
          <input type="text" value={prTitle} placeholder={t('assistant.prTitlePlaceholder')} aria-label={t('assistant.prTitlePlaceholder')}
            onChange={(e) => setPrTitle(e.target.value)} />
          <textarea value={prBody} placeholder={t('assistant.prBodyPlaceholder')} aria-label={t('assistant.prBodyPlaceholder')}
            onChange={(e) => setPrBody(e.target.value)} rows={4} />
          <button type="button" disabled={busy || !prTitle.trim()}
            onClick={() => createPr(prTitle, prBody)}>
            {t('assistant.createPr')}
          </button>
        </div>
      )}
    </>
  );
}

export function WorkspaceDiffPanel({ sessionId, onChanged }) {
  const {
    diff, truncated, error, busy, outcome,
    prOpen, setPrOpen, prTitle, setPrTitle, prBody, setPrBody,
    loadDiff, applyToRepo, discard, createPr,
  } = useWorkspaceDiff({ sessionId, onChanged });

  if (outcome) return <WorkspaceDiffOutcome outcome={outcome} />;

  const empty = diff !== null && diff.trim() === '';

  return (
    <div className="workspace-diff">
      <WorkspaceDiffBody diff={diff} truncated={truncated} error={error} empty={empty} />
      <WorkspaceDiffActions
        diff={diff} empty={empty} busy={busy}
        prOpen={prOpen} setPrOpen={setPrOpen} prTitle={prTitle} setPrTitle={setPrTitle}
        prBody={prBody} setPrBody={setPrBody} loadDiff={loadDiff}
        applyToRepo={applyToRepo} discard={discard} createPr={createPr}
      />
    </div>
  );
}
