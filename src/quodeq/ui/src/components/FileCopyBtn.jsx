import { useState, useCallback } from 'react';
import { CopyIcon, COPY_FEEDBACK_MS } from './CopyButton.jsx';
import { copyToClipboard } from '../utils/clipboard.js';
import { t } from '../strings/index.js';

// This button's own copy-feedback state, not the run/job/dim vocabulary --
// 'failed' here means "the clipboard write failed", unrelated to a job or
// run's status. Kept local rather than forced into vocab/*.js.
const COPY_STATUS = Object.freeze({ IDLE: 'idle', COPYING: 'copying', COPIED: 'copied', FAILED: 'failed' });

export default function FileCopyBtn({ display, copyText }) {
  const [status, setStatus] = useState(COPY_STATUS.IDLE);

  const handleCopy = useCallback((e) => {
    // The live-evaluation row wraps this button in a clickable container
    // that toggles open/closed on click. Stop the event so copying the
    // path doesn't also expand/collapse the row.
    e.stopPropagation();
    // Show the outcome, then fall back to the file name after the same beat
    // whether the copy worked or not.
    const settle = (outcome) => {
      setStatus(outcome);
      setTimeout(() => setStatus(COPY_STATUS.IDLE), COPY_FEEDBACK_MS);
    };
    setStatus(COPY_STATUS.COPYING);
    copyToClipboard(copyText)
      .then(() => settle(COPY_STATUS.COPIED))
      .catch((err) => {
        console.warn('Clipboard copy failed:', err?.message || err);
        settle(COPY_STATUS.FAILED);
      });
  }, [copyText]);

  const showStatusLabel = status === COPY_STATUS.COPIED || status === COPY_STATUS.FAILED;
  const statusText = status === COPY_STATUS.COPIED ? t('common.copied') : t('common.copyFailed');
  const label = showStatusLabel ? statusText : display;

  return (
    <button
      type="button"
      className="vlive-detail-file-btn"
      onClick={handleCopy}
      title={display}
    >
      <span className="vlive-detail-file-btn__label">{label}</span>
      <CopyIcon />
    </button>
  );
}
