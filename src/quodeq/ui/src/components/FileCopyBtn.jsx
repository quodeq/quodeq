import { useState, useCallback, useRef } from 'react';
import { CopyIcon, COPY_FEEDBACK_MS } from './CopyButton.jsx';
import { copyToClipboard } from '../utils/clipboard.js';
import useFittedText from '../hooks/useFittedText.js';

export default function FileCopyBtn({ display, copyText }) {
  const [status, setStatus] = useState('idle');
  const labelRef = useRef(null);

  const handleCopy = useCallback(() => {
    setStatus('copying');
    copyToClipboard(copyText)
      .then(() => {
        setStatus('copied');
        setTimeout(() => setStatus('idle'), COPY_FEEDBACK_MS);
      })
      .then(undefined, (err) => {
        console.warn('Clipboard copy failed:', err?.message || err);
        setStatus('failed');
        setTimeout(() => setStatus('idle'), COPY_FEEDBACK_MS);
      });
  }, [copyText]);

  const showStatusLabel = status === 'copied' || status === 'failed';
  const statusText = status === 'copied' ? 'Copied!' : 'Copy failed';
  const fittedDisplay = useFittedText(labelRef, showStatusLabel ? null : display);
  const label = showStatusLabel ? statusText : (fittedDisplay || display);

  return (
    <button
      type="button"
      className="vlive-detail-file-btn"
      onClick={handleCopy}
      title={display}
    >
      <span ref={labelRef} className="vlive-detail-file-btn__label">{label}</span>
      <CopyIcon />
    </button>
  );
}
