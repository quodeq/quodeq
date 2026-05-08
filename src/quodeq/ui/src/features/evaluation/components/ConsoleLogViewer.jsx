import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import usePretextHeight from '../../../hooks/usePretextHeight.js';

/**
 * ConsoleLogViewer — renders streaming job logs as one-line-per-row, with
 * each row's height pre-measured via pretext so vertical layout stays
 * stable as new lines append. A floating "follow" toggle (bottom-right,
 * outside the scroll content) pins the scroll to the bottom; manual
 * scrolling away from the bottom turns it off so the user can read past
 * output without being yanked back down.
 *
 * Logs from the runner can carry SGR escape sequences (colourised level
 * tokens, etc.). We render the visible terminal output, not the raw
 * bytes, so we strip both real ESC-prefixed CSI sequences and the bare
 * `[0;34m`-style remnants that show up when the ESC byte was lost in
 * transport. Consecutive identical lines are also collapsed — the runner
 * sometimes emits the same status both via a coloured logger and a plain
 * stdout echo, which doubled every row in the live view.
 */

const SCROLL_BOTTOM_TOLERANCE = 8;
// Real ANSI: \x1b[ ... <letter>. Bare CSI fallback: [0;34m, [0m, etc.
const ANSI_ESC_RE = /\x1b\[[\d;?]*[A-Za-z]/g;
const ANSI_BARE_RE = /\[(?:\d+(?:;\d+)*)?m/g;

// Match http(s) URLs in log lines. Trailing punctuation is excluded so a
// URL at the end of a sentence ("see https://x.com.") doesn't pull the
// terminal "." into the link.
const URL_RE = /(https?:\/\/[^\s<>"'`]+[^\s<>"'`.,;:!?)\]])/g;

function renderLineWithLinks(text) {
  if (!text) return ' ';
  const parts = [];
  let last = 0;
  let match;
  URL_RE.lastIndex = 0;
  while ((match = URL_RE.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push(
      <a
        key={match.index}
        href={match[0]}
        target="_blank"
        rel="noopener noreferrer"
        className="console-log-link"
      >
        {match[0]}
      </a>
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length > 0 ? parts : text;
}

// Don't yank the scroll viewport if the user has an active selection
// inside the given element — that would collapse their selection.
function hasActiveSelectionInside(el) {
  if (!el || typeof window === 'undefined') return false;
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) return false;
  return el.contains(sel.anchorNode) || el.contains(sel.focusNode);
}

function cleanLine(text) {
  if (text == null) return '';
  return String(text)
    .replace(ANSI_ESC_RE, '')
    .replace(ANSI_BARE_RE, '')
    // Collapse runs of inner whitespace introduced where escape codes
    // hugged a token (e.g. "[0m   [performance]" → "   [performance]").
    .replace(/[ \t]{2,}/g, ' ')
    .trimEnd();
}

// Match severity prefixes the runner's logger adds. The same payload often
// arrives twice — once via stdout from the dimension runner, once echoed
// through the logging system with this prefix — so we normalize it away
// for dedup-key purposes (the visible line keeps whichever copy lands first).
const LEVEL_PREFIX_RE = /^\s*\[(?:INFO|WARN|WARNING|ERROR|DEBUG|TRACE)\]\s*/i;

// Heartbeat lines like `  [reliability] 4m50s | 1 active (11 total) | …`
// reprint every 10s, often with identical state. Strip the duration so
// consecutive identical-state heartbeats collapse to a single row in the
// view; the next emitted heartbeat appears as soon as the state actually
// changes.
const HEARTBEAT_DURATION_RE = /(\[[\w-]+\])\s+\d+m\d+s\s+(?=\|)/;

function normalizeForDedup(line) {
  return line
    .replace(LEVEL_PREFIX_RE, '')
    .replace(HEARTBEAT_DURATION_RE, '$1 ')
    .trim();
}

function dedupeConsecutive(lines) {
  if (!lines || lines.length === 0) return lines;
  const out = [];
  let prev = null;
  for (const line of lines) {
    const key = normalizeForDedup(line);
    if (key && key === prev) continue;
    out.push(line);
    prev = key;
  }
  return out;
}

function LogLine({ text }) {
  const ref = useRef(null);
  const { height } = usePretextHeight(ref, text || ' ');
  return (
    <div ref={ref} className="console-log-line" style={height ? { minHeight: height } : undefined}>
      {renderLineWithLinks(text)}
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
  const contentRef = useRef(null);
  const [follow, setFollow] = useState(true);
  const followRef = useRef(true);
  const lastLogCount = useRef(0);
  const lastScrollHeight = useRef(0);
  const programmaticScroll = useRef(false);

  const cleanedLogs = useMemo(
    () => dedupeConsecutive((logs ?? []).map(cleanLine)),
    [logs],
  );

  useEffect(() => { followRef.current = follow; }, [follow]);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (hasActiveSelectionInside(el)) return;
    programmaticScroll.current = true;
    el.scrollTop = el.scrollHeight;
    lastScrollHeight.current = el.scrollHeight;
    requestAnimationFrame(() => { programmaticScroll.current = false; });
  }, []);

  useEffect(() => {
    const count = cleanedLogs.length;
    if (count !== lastLogCount.current) {
      lastLogCount.current = count;
      if (follow) scrollToBottom();
    }
  }, [cleanedLogs.length, follow, scrollToBottom]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      if (programmaticScroll.current) return;
      const grew = el.scrollHeight > lastScrollHeight.current;
      lastScrollHeight.current = el.scrollHeight;
      if (grew) {
        // Scroll event caused by content growth, not by the user. Keep follow
        // state untouched; if still following, snap back to bottom — unless
        // the user is mid-selection inside the scroller.
        if (followRef.current && !hasActiveSelectionInside(el)) {
          programmaticScroll.current = true;
          el.scrollTop = el.scrollHeight;
          requestAnimationFrame(() => { programmaticScroll.current = false; });
        }
        return;
      }
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      const atBottom = distanceFromBottom <= SCROLL_BOTTOM_TOLERANCE;
      setFollow((prev) => (prev === atBottom ? prev : atBottom));
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    // Resize alone never fires `scroll`, so adding a side-pane window or
    // dragging a divider would shrink clientHeight and silently leave the
    // user above the bottom — even with follow=true — until the next log
    // line. Watch BOTH the scroller (clientHeight changes) and its inner
    // content (scrollHeight changes from late `content-visibility` re-measures
    // and from new lines settling in) and re-snap on size changes.
    const snap = () => {
      if (!followRef.current) return;
      if (hasActiveSelectionInside(el)) return;
      programmaticScroll.current = true;
      el.scrollTop = el.scrollHeight;
      lastScrollHeight.current = el.scrollHeight;
      requestAnimationFrame(() => { programmaticScroll.current = false; });
    };
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(snap) : null;
    ro?.observe(el);
    if (contentRef.current) ro?.observe(contentRef.current);
    return () => {
      el.removeEventListener('scroll', onScroll);
      ro?.disconnect();
    };
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
        <div className="console-content" ref={contentRef}>
          {cleanedLogs.length === 0 ? (
            <div className="console-log-empty">Waiting for output…</div>
          ) : (
            cleanedLogs.map((line, i) => <LogLine key={i} text={line} />)
          )}
        </div>
      </div>
      <FollowToggle active={follow} onToggle={handleToggle} />
    </div>
  );
}
