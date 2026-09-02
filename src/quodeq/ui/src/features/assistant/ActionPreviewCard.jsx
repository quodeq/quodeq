import { useState } from 'react';
import { applyAssistantAction, rejectAssistantAction } from '../../api/assistant.js';
import { t } from '../../strings/index.js';

function CardSummary({ actionType, summary }) {
  if (actionType === 'dismiss_finding' || actionType === 'verify_finding') {
    const isDismiss = actionType === 'dismiss_finding';
    return (
      <div className="assistant-card-summary">
        <div className="assistant-card-name">
          {isDismiss ? t('assistant.dismissFinding') : t('assistant.verifyFinding')}
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
        {t('assistant.principlesMeta', { count: summary.principleCount, action: actionType })}
      </div>
    </div>
  );
}

function ActionStatusBanner({ status }) {
  if (status === 'applied') {
    return <div className="assistant-card-status assistant-card-status-applied">{t('assistant.applied')}</div>;
  }
  if (status === 'rejected') {
    return <div className="assistant-card-status assistant-card-status-rejected">{t('assistant.rejected')}</div>;
  }
  if (status === 'error') {
    return (
      <div className="assistant-card-status assistant-card-status-error">
        {t('assistant.somethingWrong')}
      </div>
    );
  }
  return null;
}

async function applyAction({ actionId, actionType, setStatus }) {
  setStatus('pending');
  try {
    const res = await applyAssistantAction(actionId);
    window.dispatchEvent(new CustomEvent('quodeq:assistant-action-applied', {
      detail: { actionType, scores: res?.result?.scores, delta: res?.result?.delta },
    }));
    setStatus('applied');
  } catch {
    setStatus('error');
  }
}

async function rejectAction({ actionId, setStatus }) {
  setStatus('pending');
  try {
    await rejectAssistantAction(actionId);
    setStatus('rejected');
  } catch {
    setStatus('error');
  }
}

function ActionCardButtons({ disabled, onApply, onReject }) {
  return (
    <div className="assistant-card-actions">
      <button
        type="button"
        className="assistant-card-apply"
        onClick={onApply}
        disabled={disabled}
      >
        {t('assistant.apply')}
      </button>
      <button
        type="button"
        className="assistant-card-reject"
        onClick={onReject}
        disabled={disabled}
      >
        {t('assistant.reject')}
      </button>
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

  return (
    <div className="assistant-card">
      <CardSummary actionType={actionType} summary={summary} />
      <ActionCardButtons
        disabled={disabled}
        onApply={() => applyAction({ actionId, actionType, setStatus })}
        onReject={() => rejectAction({ actionId, setStatus })}
      />
      <ActionStatusBanner status={status} />
    </div>
  );
}
