import { useEffect, useRef, useState } from 'react';
import { KEY } from '../vocab/keyboard.js';

/**
 * @param {{children: React.ReactNode, label?: string, learnMore?: {label: string, onClick: Function}}} props
 *   `learnMore` adds a link at the foot of the popover, for a help section
 *   that says more than a tooltip should.
 */
export default function HelpHint({ children, label = 'More info', learnMore }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => { if (e.key === KEY.ESCAPE) setOpen(false); };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <span className="help-hint" ref={wrapRef}>
      <button
        type="button"
        className={`help-hint-btn${open ? ' help-hint-btn--open' : ''}`}
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        ?
      </button>
      {open && (
        <span role="tooltip" className="help-hint-popover">
          {children}
          {learnMore && (
            <button type="button" className="help-hint-learn" onClick={() => { setOpen(false); learnMore.onClick(); }}>
              {learnMore.label}
            </button>
          )}
        </span>
      )}
    </span>
  );
}
