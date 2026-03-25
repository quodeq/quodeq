import { useState } from 'react';
import { CopyIcon, COPY_FEEDBACK_MS } from './CopyButton.jsx';
import { copyToClipboard } from '../utils/clipboard.js';

export default function FileCopyBtn({ display, copyText }) {
  const [status, setStatus] = useState('idle');
  const label = status === 'copied' ? 'Copied!' : status === 'failed' ? 'Copy failed' : display;
  return (
    <button
      type="button"
      className="vlive-detail-file-btn"
      onClick={() => {
        copyToClipboard(copyText).then(() => {
          setStatus('copied');
          setTimeout(() => setStatus('idle'), COPY_FEEDBACK_MS);
        }).catch(() => {
          setStatus('failed');
          setTimeout(() => setStatus('idle'), COPY_FEEDBACK_MS);
        });
      }}
    >
      {label}
      <CopyIcon />
    </button>
  );
}
