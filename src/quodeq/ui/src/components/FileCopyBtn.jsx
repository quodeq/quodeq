import { useState, useCallback } from 'react';
import { CopyIcon, COPY_FEEDBACK_MS } from './CopyButton.jsx';
import { copyToClipboard } from '../utils/clipboard.js';
import { t } from '../strings/index.js';

export default function FileCopyBtn({ display, copyText }) {
  const [status, setStatus] = useState('idle');

  const handleCopy = useCallback((e) => {
    // The live-evaluation row wraps this button in a clickable container
    // that toggles open/closed on click. Stop the event so copying the
    // path doesn't also expand/collapse the row.
    e.stopPropagation();
    // Show the outcome, then fall back to the file name after the same beat
    // whether the copy worked or not.
    const settle = (outcome) => {
      setStatus(outcome);
      setTimeout(() => setStatus('idle'), COPY_FEEDBACK_MS);
    };
    setStatus('copying');
    copyToClipboard(copyText)
      .then(() => settle('copied'))
      .catch((err) => {
        console.warn('Clipboard copy failed:', err?.message || err);
        settle('failed');
      });
  }, [copyText]);

  const showStatusLabel = status === 'copied' || status === 'failed';
  const statusText = status === 'copied' ? t('common.copied') : t('common.copyFailed');
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
