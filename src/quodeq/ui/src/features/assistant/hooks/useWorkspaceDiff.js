import { useCallback, useEffect, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

// PR fail-soft: branch kept, worktree still active. Do NOT lock the panel;
// surface the message and let the user retry, apply, or discard.
function applyPrOutcome(res, setOutcome, setError) {
  if (res.pushed) {
    // Branch is on the remote; local apply is moot. Terminal message.
    setOutcome({ kind: 'pr', message: res.message || null, prUrl: null });
  } else {
    // Push failed: changes restored to the worktree; keep buttons to retry/apply/discard.
    setError(res.message || t('assistant.prNotCreated'));
  }
}

/**
 * WorkspaceDiffPanel.jsx's diff-loading, action (apply/PR/discard) and PR-form
 * state. Extracted verbatim.
 */
export function useWorkspaceDiff({ sessionId, onChanged }) {
  const {
    applyAssistantWorkspace, createAssistantWorkspacePr,
    discardAssistantWorkspace, fetchAssistantWorkspaceDiff,
  } = useApi();
  const [diff, setDiff] = useState(null);
  const [truncated, setTruncated] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState(null); // {kind, message, prUrl}
  const [prOpen, setPrOpen] = useState(false);
  const [prTitle, setPrTitle] = useState(t('assistant.defaultPrTitle'));
  const [prBody, setPrBody] = useState('');

  const loadDiff = useCallback(() => {
    let cancelled = false;
    setDiff(null); setError(null);
    fetchAssistantWorkspaceDiff(sessionId)
      .then((d) => { if (!cancelled) { setDiff(d.diff ?? ''); setTruncated(!!d.truncated); } })
      // WORKSPACE_DIFF_FAILED carries a `code` (see assistant_workspace_routes.py) --
      // route it through apiErrorMessage instead of always showing the raw text.
      .catch((err) => { if (!cancelled) setError(apiErrorMessage(err, 'assistant.diffLoadFailed')); });
    return () => { cancelled = true; };
  }, [sessionId]);

  useEffect(() => loadDiff(), [loadDiff]);

  const act = useCallback(async (fn, kind) => {
    setBusy(true); setError(null);
    try {
      const res = await fn();
      if (kind === 'pr' && !res.prUrl) {
        applyPrOutcome(res, setOutcome, setError);
        onChanged?.();
        return;
      }
      setOutcome({ kind, message: res.message || null, prUrl: res.prUrl || null });
      onChanged?.();
    } catch (err) {
      // TURN_IN_PROGRESS / WORKSPACE_DISCARD_FAILED carry a `code` (see
      // assistant_workspace_routes.py) -- route through apiErrorMessage
      // instead of always showing the raw text.
      setError(apiErrorMessage(err, 'assistant.workspaceActionFailed'));
    } finally {
      setBusy(false);
    }
  }, [onChanged]);

  return {
    diff, truncated, error, busy, outcome,
    prOpen, setPrOpen, prTitle, setPrTitle, prBody, setPrBody,
    loadDiff, act,
  };
}
