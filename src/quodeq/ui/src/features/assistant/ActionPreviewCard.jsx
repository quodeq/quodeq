import { useState } from 'react';
import { applyAssistantAction, rejectAssistantAction } from '../../api/assistant.js';

function CardSummary({ actionType, summary }) {
  if (actionType === 'dismiss_finding' || actionType === 'verify_finding') {
    const isDismiss = actionType === 'dismiss_finding';
    return (
      <div className="assistant-card-summary">
        <div className="assistant-card-name">
          {isDismiss ? 'Dismiss finding' : 'Mark finding as verified'}
        </div>
        <div className="assistant-card-meta">
          {summary.req} &middot; {summary.file}:{summary.line}
        </div>
        <div className="assistant-card-note">{isDismiss ? summary.reason : summary.note}</div>
      </div>
    );
  }
  return (
    <div className="assistant-card-summary">
      <div className="assistant-card-name">{summary.name}</div>
      <div className="assistant-card-meta">
        {summary.principleCount} principles &middot; {actionType}
      </div>
    </div>
  );
}

/**
 * Renders the server-canonical summary of a proposed assistant action
 * (name, principle count, action type) with Apply / Reject controls.
 *
 * No raw model markdown is rendered here — only the structured summary
 * fields provided by the server.
 */
export function ActionPreviewCard({ action }) {
  const [status, setStatus] = useState('idle');
  const { actionId, actionType, summary } = action;

  const disabled = status !== 'idle';

  async function handleApply() {
    setStatus('pending');
    try {
      await applyAssistantAction(actionId);
      setStatus('applied');
    } catch {
      setStatus('error');
    }
  }

  async function handleReject() {
    setStatus('pending');
    try {
      await rejectAssistantAction(actionId);
      setStatus('rejected');
    } catch {
      setStatus('error');
    }
  }

  return (
    <div className="assistant-card">
      <CardSummary actionType={actionType} summary={summary} />
      <div className="assistant-card-actions">
        <button
          type="button"
          className="assistant-card-apply"
          onClick={handleApply}
          disabled={disabled}
        >
          Apply
        </button>
        <button
          type="button"
          className="assistant-card-reject"
          onClick={handleReject}
          disabled={disabled}
        >
          Reject
        </button>
      </div>
      {status === 'applied' && (
        <div className="assistant-card-status assistant-card-status-applied">Applied ✓</div>
      )}
      {status === 'rejected' && (
        <div className="assistant-card-status assistant-card-status-rejected">Rejected</div>
      )}
      {status === 'error' && (
        <div className="assistant-card-status assistant-card-status-error">
          Something went wrong. Please try again.
        </div>
      )}
    </div>
  );
}
