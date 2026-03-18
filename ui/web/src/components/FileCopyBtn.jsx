import { useState } from 'react';
import { CopyIcon } from './CopyButton.jsx';

const COPY_FEEDBACK_MS = 1500;

export default function FileCopyBtn({ display, copyText }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="vlive-detail-file-btn"
      onClick={() => {
        navigator.clipboard.writeText(copyText);
        setCopied(true);
        setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
      }}
    >
      {copied ? 'Copied!' : display}
      <CopyIcon />
    </button>
  );
}
