import { memo, useEffect, useMemo, useRef, useState, useCallback } from 'react';
import usePretextHeight from '../../../hooks/usePretextHeight.js';
import { t } from '../../../strings/index.js';
import { advancePipeline, trailerText } from './consoleLogPipeline.js';

/**
 * ConsoleLogViewer, renders streaming job logs as one-line-per-row, with
 * each row's height pre-measured via pretext so vertical layout stays
 * stable as new lines append. A floating "follow" toggle (bottom-right,
 * outside the scroll content) pins the scroll to the bottom; manual
 * scrolling away from the bottom turns it off so the user can read past
 * output without being yanked back down.
 *
 * Cleaning (SGR escape stripping) and consecutive-duplicate folding live in
 * consoleLogPipeline.js, which does them incrementally: each batch cleans
 * only its new lines, and rows keep their sequence number as the React key
 * so a front trim at the source's line cap does not re-render every row.
 */

const SCROLL_BOTTOM_TOLERANCE = 8;

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

// Jump the viewport to the bottom, marking the move as ours so the scroll
// listener does not read it as the user leaving the tail. A live selection
// inside the log wins: scrolling would collapse it.
function snapToBottom(el, programmaticScroll, lastScrollHeight) {
  if (hasActiveSelectionInside(el)) return;
  programmaticScroll.current = true;
  el.scrollTop = el.scrollHeight;
  lastScrollHeight.current = el.scrollHeight;
  requestAnimationFrame(() => { programmaticScroll.current = false; });
}

// Memoized: with stable seq keys an existing row's text never changes, so
// a new batch re-renders (and re-measures via pretext) only the new rows.
const LogLine = memo(function LogLine({ text }) {
  const ref = useRef(null);
  const { height } = usePretextHeight(ref, text || ' ');
  return (
    <div ref={ref} className="console-log-line" style={height ? { minHeight: height } : undefined}>
      {renderLineWithLinks(text)}
    </div>
  );
});

function FollowToggle({ active, onToggle }) {
  return (
    <button
      type="button"
      className={`console-follow-btn${active ? ' console-follow-btn--active' : ''}`}
      title={active ? t('evaluate.followingTitle') : t('evaluate.followTitle')}
      aria-pressed={active}
      onClick={onToggle}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polyline points="6 9 12 15 18 9" />
      </svg>
      <span>{t('evaluate.follow')}</span>
    </button>
  );
}

// Resize alone never fires `scroll`, so adding a side-pane window or
// dragging a divider would shrink clientHeight and silently leave the
// user above the bottom — even with follow=true — until the next log
// line. Watch BOTH the scroller (clientHeight changes) and its inner
// content (scrollHeight changes from late `content-visibility` re-measures
// and from new lines settling in) and re-snap on size changes.
function makeScrollWatcherEffect({ scrollRef, contentRef, followRef, programmaticScroll, lastScrollHeight, setFollow }) {
  return () => {
    const el = scrollRef.current;
    if (!el) return undefined;
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
    const snap = () => {
      if (!followRef.current) return;
      snapToBottom(el, programmaticScroll, lastScrollHeight);
    };
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(snap) : null;
    ro?.observe(el);
    if (contentRef.current) ro?.observe(contentRef.current);
    return () => {
      el.removeEventListener('scroll', onScroll);
      ro?.disconnect();
    };
  };
}

function useConsoleAutoScroll(logCount) {
  const scrollRef = useRef(null);
  const contentRef = useRef(null);
  const [follow, setFollow] = useState(true);
  const followRef = useRef(true);
  const lastLogCount = useRef(0);
  const lastScrollHeight = useRef(0);
  const programmaticScroll = useRef(false);

  useEffect(() => { followRef.current = follow; }, [follow]);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) snapToBottom(el, programmaticScroll, lastScrollHeight);
  }, []);

  useEffect(() => {
    if (logCount !== lastLogCount.current) {
      lastLogCount.current = logCount;
      if (follow) scrollToBottom();
    }
  }, [logCount, follow, scrollToBottom]);

  useEffect(
    makeScrollWatcherEffect({ scrollRef, contentRef, followRef, programmaticScroll, lastScrollHeight, setFollow }),
    [],
  );

  const handleToggle = useCallback(() => {
    setFollow((prev) => {
      const next = !prev;
      if (next) scrollToBottom();
      return next;
    });
  }, [scrollToBottom]);

  return { scrollRef, contentRef, follow, handleToggle };
}

const TRAILER_KEY = 'trailer';

// The pipeline state lives in a ref so each batch builds on the last one.
// advancePipeline never mutates its input and is keyed by seqs, not by
// render history, so a doubled (StrictMode) or discarded render is harmless.
//
// `sourceId` covers advancePipeline's blind spot: it tells appended lines
// from trimmed ones by comparing (firstSeq, endSeq) pairs, which cannot
// tell two DIFFERENT sources apart if one happens to reuse the seq range
// the other left off at (e.g. two hook instances that both start counting
// at 0). A caller whose source can be swapped out while this component
// stays mounted (a job id, a provider identity) passes it so a swap
// throws the ref away instead of feeding it to advancePipeline as if it
// were a continuation of the old source.
function useLogRows(logs, firstSeq, sourceId) {
  const stateRef = useRef(null);
  const sourceIdRef = useRef(sourceId);
  return useMemo(() => {
    if (sourceId !== sourceIdRef.current) {
      stateRef.current = null;
      sourceIdRef.current = sourceId;
    }
    stateRef.current = advancePipeline(stateRef.current, logs, firstSeq);
    return stateRef.current;
  }, [logs, firstSeq, sourceId]);
}

export default function ConsoleLogViewer({ logs, firstSeq, trailer = null, sourceId }) {
  const pipeline = useLogRows(logs, firstSeq, sourceId);
  const trailerLine = trailerText(pipeline, trailer);
  // Same count the auto-scroll hook always got: visible rows incl. the trailer.
  const lineCount = pipeline.rows.length + (trailerLine == null ? 0 : 1);
  const { scrollRef, contentRef, follow, handleToggle } = useConsoleAutoScroll(lineCount);

  return (
    <div className="console-shell">
      <div className="console-scroll" ref={scrollRef}>
        <div className="console-content" ref={contentRef}>
          {lineCount === 0 ? (
            <div className="console-log-empty">{t('evaluate.waitingForOutput')}</div>
          ) : (
            <>
              {pipeline.rows.map((row) => <LogLine key={row.seq} text={row.text} />)}
              {trailerLine != null && <LogLine key={TRAILER_KEY} text={trailerLine} />}
            </>
          )}
        </div>
      </div>
      <FollowToggle active={follow} onToggle={handleToggle} />
    </div>
  );
}
