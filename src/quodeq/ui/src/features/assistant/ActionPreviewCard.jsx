import { useState } from 'react';
import { applyAssistantAction, rejectAssistantAction } from '../../api/assistant.js';
import { notifyAssistantActionApplied } from '../../constants.js';
import { t } from '../../strings/index.js';

// Server-side action kinds this card knows how to summarise. Anything else
// falls through to the generic standard-edit summary.
const ACTION_TYPE = Object.freeze({ DISMISS_FINDING: 'dismiss_finding', VERIFY_FINDING: 'verify_finding' });

// Local lifecycle of one card: idle until the user picks, pending while the
// request is in flight, then the terminal outcome. Drives both the banner and
// the disabled state of the buttons.
const CARD_STATUS = Object.freeze({
  IDLE: 'idle', PENDING: 'pending', APPLIED: 'applied', REJECTED: 'rejected', ERROR: 'error',
});

function CardSummary({ actionType, summary }) {
  if (actionType === ACTION_TYPE.DISMISS_FINDING || actionType === ACTION_TYPE.VERIFY_FINDING) {
    const isDismiss = actionType === ACTION_TYPE.DISMISS_FINDING;
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
  if (status === CARD_STATUS.APPLIED) {
    return <div className="assistant-card-status assistant-card-status-applied">{t('assistant.applied')}</div>;
  }
  if (status === CARD_STATUS.REJECTED) {
    return <div className="assistant-card-status assistant-card-status-rejected">{t('assistant.rejected')}</div>;
  }
  if (status === CARD_STATUS.ERROR) {
    return (
      <div className="assistant-card-status assistant-card-status-error">
        {t('assistant.somethingWrong')}
      </div>
    );
  }
  return null;
}

// Apply and reject are the same state machine: pending while the request is
// in flight, then a terminal status, and ERROR on any failure. `run` performs
// the request and `done` is the status a success lands on.
async function runCardAction({ setStatus, run, done, logLabel }) {
  setStatus(CARD_STATUS.PENDING);
  try {
    await run();
    setStatus(done);
  } catch (err) {
    console.warn(logLabel, err);
    setStatus(CARD_STATUS.ERROR);
  }
}

async function applyAction({ actionId, actionType, setStatus }) {
  await runCardAction({
    setStatus,
    run: async () => {
      const res = await applyAssistantAction(actionId);
      notifyAssistantActionApplied({ actionType, scores: res?.result?.scores, delta: res?.result?.delta });
    },
    done: CARD_STATUS.APPLIED,
    logLabel: '[ActionPreviewCard] apply action failed:',
  });
}

async function rejectAction({ actionId, setStatus }) {
  await runCardAction({
    setStatus,
    run: () => rejectAssistantAction(actionId),
    done: CARD_STATUS.REJECTED,
    logLabel: '[ActionPreviewCard] reject action failed:',
  });
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
  const [status, setStatus] = useState(CARD_STATUS.IDLE);
  const { actionId, actionType, summary } = action;

  const disabled = status !== CARD_STATUS.IDLE;

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
