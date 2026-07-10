import React, { useCallback, useEffect, useState } from 'react';
import {
  applyAssistantWorkspace, createAssistantWorkspacePr,
  discardAssistantWorkspace, fetchAssistantWorkspaceDiff,
} from '../../api/assistant.js';

export function classifyDiffLine(line) {
  if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff --git')) return 'wsdiff-file';
  if (line.startsWith('@@')) return 'wsdiff-hunk';
  if (line.startsWith('+')) return 'wsdiff-add';
  if (line.startsWith('-')) return 'wsdiff-del';
  return 'wsdiff-ctx';
}

export function WorkspaceDiffPanel({ sessionId, onChanged }) {
  const [diff, setDiff] = useState(null);
  const [truncated, setTruncated] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState(null); // {kind, message, prUrl}
  const [prOpen, setPrOpen] = useState(false);
  const [prTitle, setPrTitle] = useState('Quodeq assistant fix');
  const [prBody, setPrBody] = useState('');

  const loadDiff = useCallback(() => {
    let cancelled = false;
    setDiff(null); setError(null);
    fetchAssistantWorkspaceDiff(sessionId)
      .then((d) => { if (!cancelled) { setDiff(d.diff ?? ''); setTruncated(!!d.truncated); } })
      .catch((err) => { if (!cancelled) setError(err?.message || String(err)); });
    return () => { cancelled = true; };
  }, [sessionId]);

  useEffect(() => loadDiff(), [loadDiff]);

  const act = useCallback(async (fn, kind) => {
    setBusy(true); setError(null);
    try {
      const res = await fn();
      // PR fail-soft: branch kept, worktree still active. Do NOT lock the panel;
      // surface the message and let the user retry, apply, or discard.
      if (kind === 'pr' && !res.prUrl) {
        if (res.pushed) {
          // Branch is on the remote; local apply is moot. Terminal message.
          setOutcome({ kind: 'pr', message: res.message || null, prUrl: null });
        } else {
          // Push failed: changes restored to the worktree; keep buttons to retry/apply/discard.
          setError(res.message || 'Branch kept locally; PR was not created.');
        }
        onChanged?.();
        return;
      }
      setOutcome({ kind, message: res.message || null, prUrl: res.prUrl || null });
      onChanged?.();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [onChanged]);

  if (outcome) {
    return (
      <div className="workspace-diff">
        <p className="workspace-diff-outcome" role="status" aria-live="polite">
          {outcome.kind === 'applied' && 'Changes applied to your working tree (uncommitted). Review and commit them yourself.'}
          {outcome.kind === 'discarded' && 'Changes discarded. The worktree and branch were removed.'}
          {outcome.kind === 'pr' && (outcome.prUrl
            ? <>PR created: <a href={outcome.prUrl} target="_blank" rel="noreferrer">{outcome.prUrl}</a></>
            : (outcome.message || 'Branch kept locally.'))}
        </p>
      </div>
    );
  }

  const empty = diff !== null && diff.trim() === '';

  return (
    <div className="workspace-diff">
      {truncated && (
        <p className="workspace-diff-warning" role="alert">
          Diff truncated at 2 MB for display. Apply and Create PR act on the full set of changes, which is larger than shown here.
        </p>
      )}
      {error && <p className="workspace-diff-error" role="alert">{error}</p>}
      {diff === null && !error && <p aria-live="polite">Loading diff...</p>}
      {empty && <p className="workspace-diff-empty">No changes in this worktree.</p>}
      {diff !== null && !empty && (
        <pre className="workspace-diff-body">
          {diff.split('\n').map((line, i) => (
            // eslint-disable-next-line react/no-array-index-key
            <span key={i} className={classifyDiffLine(line)}>{line}{'\n'}</span>
          ))}
        </pre>
      )}
      <div className="workspace-diff-actions">
        <button type="button" disabled={busy} onClick={() => loadDiff()}>
          Refresh
        </button>
        <button type="button" disabled={busy || !diff || empty}
          onClick={() => act(() => applyAssistantWorkspace(sessionId), 'applied')}>
          Apply to repo
        </button>
        <button type="button" disabled={busy || !diff || empty}
          onClick={() => setPrOpen((v) => !v)} aria-expanded={prOpen}>
          Create PR...
        </button>
        <button type="button" disabled={busy}
          onClick={() => act(() => discardAssistantWorkspace(sessionId), 'discarded')}>
          Discard
        </button>
      </div>
      {prOpen && (
        <div className="workspace-diff-pr">
          <input type="text" value={prTitle} placeholder="PR title" aria-label="PR title"
            onChange={(e) => setPrTitle(e.target.value)} />
          <textarea value={prBody} placeholder="PR description" aria-label="PR description"
            onChange={(e) => setPrBody(e.target.value)} rows={4} />
          <button type="button" disabled={busy || !prTitle.trim()}
            onClick={() => act(() => createAssistantWorkspacePr(sessionId,
              { title: prTitle, body: prBody }), 'pr')}>
            Create PR
          </button>
        </div>
      )}
    </div>
  );
}
