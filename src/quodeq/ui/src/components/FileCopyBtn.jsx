import { useState } from 'react';
import { CopyIcon, COPY_FEEDBACK_MS } from './CopyButton.jsx';
import { copyToClipboard } from '../utils/clipboard.js';

export default function FileCopyBtn({ display, copyText }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="vlive-detail-file-btn"
      onClick={() => {
        copyToClipboard(copyText).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
        }).catch(() => { setCopied(false); });
      }}
    >
      {copied ? 'Copied!' : display}
      <CopyIcon />
    </button>
  );
}
