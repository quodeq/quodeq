import { useState } from 'react';

export const COPY_FEEDBACK_MS = 1500;

const ICON_SIZE = 12;
const ICON_VIEWBOX = "0 0 24 24";

export function SparkleIcon() {
  return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox={ICON_VIEWBOX} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5z" />
      <path d="M18 14l1 3 3 1-3 1-1 3-1-3-3-1 3-1z" />
    </svg>
  );
}

export function CopyIcon() {
  return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox={ICON_VIEWBOX} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export function FileTextIcon() {
  return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox={ICON_VIEWBOX} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="9" y1="13" x2="15" y2="13" />
      <line x1="9" y1="17" x2="15" y2="17" />
    </svg>
  );
}

export function TerminalIcon() {
  return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox={ICON_VIEWBOX} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
  );
}

// Chevron up = maximize (the bottom drawer grows upward); chevron down =
// restore (it collapses back down).
export function ChevronUpIcon() {
  return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox={ICON_VIEWBOX} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="6 15 12 9 18 15" />
    </svg>
  );
}

export function ChevronDownIcon() {
  return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox={ICON_VIEWBOX} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

export function GlobeIcon() {
  return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox={ICON_VIEWBOX} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

export default function CopyButton({ onClick, label, className, icon, 'aria-label': ariaLabel }) {
  const [copied, setCopied] = useState(false);

  const handleClick = () => {
    onClick();
    setCopied(true);
    setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
  };

  return (
    <button className={className || 'detail-copy-btn'} onClick={handleClick} aria-label={ariaLabel}>
      {icon}
      {copied ? 'Copied!' : label}
      {!icon && <CopyIcon />}
    </button>
  );
}
