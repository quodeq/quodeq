import React from 'react';
import { WorkspaceDiffPanel } from '../assistant/WorkspaceDiffPanel.jsx';

/** Side-pane window spec for the assistant's pending worktree changes. */
export function workspaceDiffSpec({ sessionId, onChanged }) {
  if (!sessionId) return null;
  return {
    id: `workspace-diff:${sessionId}`,
    type: 'workspace-diff',
    title: 'Assistant changes',
    render: () => <WorkspaceDiffPanel sessionId={sessionId} onChanged={onChanged} />,
  };
}
