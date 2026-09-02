import React from 'react';
import {
  applyAssistantWorkspace, createAssistantWorkspacePr, discardAssistantWorkspace,
} from '../../api/assistant.js';
import { t } from '../../strings/index.js';
import { useWorkspaceDiff } from './hooks/useWorkspaceDiff.js';

export function classifyDiffLine(line) {
  if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff --git')) return 'wsdiff-file';
  if (line.startsWith('@@')) return 'wsdiff-hunk';
  if (line.startsWith('+')) return 'wsdiff-add';
  if (line.startsWith('-')) return 'wsdiff-del';
  return 'wsdiff-ctx';
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
        <pre className="workspace-diff-body">
          {diff.split('\n').map((line, i) => (
            // eslint-disable-next-line react/no-array-index-key
            <span key={i} className={classifyDiffLine(line)}>{line}{'\n'}</span>
          ))}
        </pre>
      )}
    </>
  );
}

function WorkspaceDiffActions({ sessionId, diff, empty, busy, prOpen, setPrOpen, prTitle, setPrTitle, prBody, setPrBody, loadDiff, act }) {
  return (
    <>
      <div className="workspace-diff-actions">
        <button type="button" disabled={busy} onClick={() => loadDiff()}>
          {t('assistant.refresh')}
        </button>
        <button type="button" disabled={busy || !diff || empty}
          onClick={() => act(() => applyAssistantWorkspace(sessionId), 'applied')}>
          {t('assistant.applyToRepo')}
        </button>
        <button type="button" disabled={busy || !diff || empty}
          onClick={() => setPrOpen((v) => !v)} aria-expanded={prOpen}>
          {t('assistant.createPrEllipsis')}
        </button>
        <button type="button" disabled={busy}
          onClick={() => act(() => discardAssistantWorkspace(sessionId), 'discarded')}>
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
            onClick={() => act(() => createAssistantWorkspacePr(sessionId,
              { title: prTitle, body: prBody }), 'pr')}>
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
    loadDiff, act,
  } = useWorkspaceDiff({ sessionId, onChanged });

  if (outcome) return <WorkspaceDiffOutcome outcome={outcome} />;

  const empty = diff !== null && diff.trim() === '';

  return (
    <div className="workspace-diff">
      <WorkspaceDiffBody diff={diff} truncated={truncated} error={error} empty={empty} />
      <WorkspaceDiffActions
        sessionId={sessionId} diff={diff} empty={empty} busy={busy}
        prOpen={prOpen} setPrOpen={setPrOpen} prTitle={prTitle} setPrTitle={setPrTitle}
        prBody={prBody} setPrBody={setPrBody} loadDiff={loadDiff} act={act}
      />
    </div>
  );
}
