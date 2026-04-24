import { useEffect, useRef, useState, useCallback } from 'react';
import usePretextHeight from '../../../hooks/usePretextHeight.js';

/**
 * ConsoleLogViewer — renders streaming job logs as one-line-per-row, with
 * each row's height pre-measured via pretext so vertical layout stays
 * stable as new lines append. A floating "follow" toggle (bottom-right,
 * outside the scroll content) pins the scroll to the bottom; manual
 * scrolling away from the bottom turns it off so the user can read past
 * output without being yanked back down.
 */

const SCROLL_BOTTOM_TOLERANCE = 8;

function LogLine({ text }) {
  const ref = useRef(null);
  const { height } = usePretextHeight(ref, text || ' ');
  return (
    <div ref={ref} className="console-log-line" style={height ? { minHeight: height } : undefined}>
      {text || '\u00A0'}
    </div>
  );
}

function FollowToggle({ active, onToggle }) {
  return (
    <button
      type="button"
      className={`console-follow-btn${active ? ' console-follow-btn--active' : ''}`}
      title={active ? 'Following — click to stop' : 'Click to follow new output'}
      aria-pressed={active}
      onClick={onToggle}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polyline points="6 9 12 15 18 9" />
      </svg>
      <span>follow</span>
    </button>
  );
}

export default function ConsoleLogViewer({ logs }) {
  const scrollRef = useRef(null);
  const [follow, setFollow] = useState(true);
  const lastLogCount = useRef(0);
  const programmaticScroll = useRef(false);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    programmaticScroll.current = true;
    el.scrollTop = el.scrollHeight;
    requestAnimationFrame(() => { programmaticScroll.current = false; });
  }, []);

  useEffect(() => {
    const count = logs?.length || 0;
    if (count !== lastLogCount.current) {
      lastLogCount.current = count;
      if (follow) scrollToBottom();
    }
  }, [logs?.length, follow, scrollToBottom]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      if (programmaticScroll.current) return;
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      const atBottom = distanceFromBottom <= SCROLL_BOTTOM_TOLERANCE;
      setFollow((prev) => (prev === atBottom ? prev : atBottom));
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  const handleToggle = useCallback(() => {
    setFollow((prev) => {
      const next = !prev;
      if (next) scrollToBottom();
      return next;
    });
  }, [scrollToBottom]);

  return (
    <div className="console-shell">
      <div className="console-scroll" ref={scrollRef}>
        {!logs || logs.length === 0 ? (
          <div className="console-log-empty">Waiting for output\u2026</div>
        ) : (
          logs.map((line, i) => <LogLine key={i} text={line} />)
        )}
      </div>
      <FollowToggle active={follow} onToggle={handleToggle} />
    </div>
  );
}
