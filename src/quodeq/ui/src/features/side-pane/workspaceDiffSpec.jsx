import React from 'react';
import { WorkspaceDiffPanel } from '../assistant/WorkspaceDiffPanel.jsx';

/** Side-pane window spec for the assistant's pending worktree changes.
 *  `key` (the worktree's createdAt) folds into the window id so a NEW worktree
 *  opens a FRESH window rather than being deduped onto a prior worktree's stale
 *  "changes applied" outcome panel that lingers mounted. */
export function workspaceDiffSpec({ sessionId, key, onChanged }) {
  if (!sessionId) return null;
  const id = `workspace-diff:${sessionId}:${key || 'current'}`;
  return {
    id,
    type: 'workspace-diff',
    title: 'Assistant changes',
    render: () => <WorkspaceDiffPanel sessionId={sessionId} onChanged={onChanged} />,
  };
}
