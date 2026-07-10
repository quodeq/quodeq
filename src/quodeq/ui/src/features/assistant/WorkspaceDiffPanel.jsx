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
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState(null); // {kind, message, prUrl}
  const [prOpen, setPrOpen] = useState(false);
  const [prTitle, setPrTitle] = useState('Quodeq assistant fix');
  const [prBody, setPrBody] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchAssistantWorkspaceDiff(sessionId)
      .then((d) => { if (!cancelled) setDiff(d.diff ?? ''); })
      .catch((err) => { if (!cancelled) setError(err?.message || String(err)); });
    return () => { cancelled = true; };
  }, [sessionId]);

  const act = useCallback(async (fn, kind) => {
    setBusy(true); setError(null);
    try {
      const res = await fn();
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
        <p className="workspace-diff-outcome">
          {outcome.kind === 'applied' && 'Changes applied to your working tree (uncommitted). Review and commit them yourself.'}
          {outcome.kind === 'discarded' && 'Changes discarded. The worktree and branch were removed.'}
          {outcome.kind === 'pr' && (outcome.prUrl
            ? <>PR created: <a href={outcome.prUrl} target="_blank" rel="noreferrer">{outcome.prUrl}</a></>
            : (outcome.message || 'Branch kept locally.'))}
        </p>
      </div>
    );
  }

  return (
    <div className="workspace-diff">
      {error && <p className="workspace-diff-error">{error}</p>}
      {diff === null && !error && <p>Loading diff...</p>}
      {diff !== null && (
        <pre className="workspace-diff-body">
          {diff.split('\n').map((line, i) => (
            // eslint-disable-next-line react/no-array-index-key
            <span key={i} className={classifyDiffLine(line)}>{line}{'\n'}</span>
          ))}
        </pre>
      )}
      <div className="workspace-diff-actions">
        <button type="button" disabled={busy || !diff}
          onClick={() => act(() => applyAssistantWorkspace(sessionId), 'applied')}>
          Apply to repo
        </button>
        <button type="button" disabled={busy || !diff}
          onClick={() => setPrOpen((v) => !v)}>
          Create PR...
        </button>
        <button type="button" disabled={busy}
          onClick={() => act(() => discardAssistantWorkspace(sessionId), 'discarded')}>
          Discard
        </button>
      </div>
      {prOpen && (
        <div className="workspace-diff-pr">
          <input type="text" value={prTitle} placeholder="PR title"
            onChange={(e) => setPrTitle(e.target.value)} />
          <textarea value={prBody} placeholder="PR description"
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
