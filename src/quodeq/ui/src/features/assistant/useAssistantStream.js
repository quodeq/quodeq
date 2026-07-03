import { useCallback, useEffect, useRef, useState } from 'react';
import { assistantEventsUrl } from '../../api/assistant.js';

const INACTIVITY_MS = 60000;

export function useAssistantStream(sessionId, { onDone } = {}) {
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const pending = useRef(''); const raf = useRef(null); const timer = useRef(null);
  const inactivity = useRef(null); const onDoneRef = useRef(onDone);
  // When true, the next flushed token starts a NEW assistant bubble instead of
  // appending to the last one — set on each turn's terminal frame so turn 2's
  // answer doesn't concatenate onto turn 1's ("A"+"B" → "AB"). One SSE stream
  // serves the whole session, so bubbles from separate turns must stay split.
  const turnBoundary = useRef(false);
  onDoneRef.current = onDone;

  const reset = useCallback(() => { setMessages([]); setError(null); }, []);

  useEffect(() => {
    if (!sessionId) { setStreaming(false); return undefined; }
    setMessages([]); setError(null); setStreaming(true); pending.current = '';
    turnBoundary.current = false;

    const flushTokens = () => {
      if (raf.current != null) { cancelAnimationFrame(raf.current); raf.current = null; }
      if (timer.current != null) { clearTimeout(timer.current); timer.current = null; }
      const chunk = pending.current; if (!chunk) return;
      pending.current = '';
      const startNewBubble = turnBoundary.current;
      turnBoundary.current = false;
      setMessages((prev) => {
        const next = prev.slice();
        const last = next[next.length - 1];
        if (!startNewBubble && last && last.role === 'assistant') {
          next[next.length - 1] = { ...last, text: last.text + chunk };
        } else {
          next.push({ role: 'assistant', text: chunk });
        }
        return next;
      });
    };
    const scheduleFlush = () => {
      if (raf.current == null) raf.current = requestAnimationFrame(flushTokens);
      if (timer.current == null) timer.current = setTimeout(flushTokens, 50);
    };
    const append = (msg) => setMessages((prev) => [...prev, msg]);
    const resetInactivity = () => {
      if (inactivity.current) clearTimeout(inactivity.current);
      inactivity.current = setTimeout(() => { es.close(); setStreaming(false); setError('stream timed out'); }, INACTIVITY_MS);
    };

    const es = new EventSource(assistantEventsUrl(sessionId, 0));
    // End the TURN (flush, clear spinner, mark a boundary, notify the
    // provider) WITHOUT closing the connection — the stream stays open so the
    // next turn's frames still arrive. The EventSource is only closed in the
    // effect cleanup (sessionId change / unmount).
    const endTurn = () => { flushTokens(); setStreaming(false);
      turnBoundary.current = true; onDoneRef.current?.(); };
    // First content frame of a turn: re-arm streaming and, once a turn
    // boundary has been crossed, clear any stale stream error from the prior
    // turn so a retry starts clean.
    const beginContent = () => { if (turnBoundary.current) setError(null); setStreaming(true); };

    es.onmessage = (e) => {
      resetInactivity();
      let frame; try { frame = JSON.parse(e.data); } catch { return; }
      if (frame.type === 'token') { beginContent(); pending.current += frame.text || ''; scheduleFlush(); }
      else if (frame.type === 'tool_call') { beginContent(); flushTokens(); append({ role: 'tool', name: frame.name }); }
      else if (frame.type === 'action_draft') { beginContent(); flushTokens();
        append({ role: 'action', actionId: frame.actionId, actionType: frame.actionType, summary: frame.summary }); }
      else if (frame.type === 'warning') { beginContent(); flushTokens(); append({ role: 'warning', message: frame.message }); }
      else if (frame.type === 'error') { flushTokens(); setError(frame.message || 'error'); endTurn(); }
      else if (frame.type === 'done') { endTurn(); }
      else if (frame.type === 'heartbeat') { /* liveness only: resetInactivity() already ran above */ }
    };
    es.addEventListener('done', endTurn);
    es.onerror = () => { if (es.readyState === 2) { setStreaming(false); setError((p) => p || 'disconnected'); } };
    resetInactivity();

    return () => { es.close();
      [raf.current && cancelAnimationFrame(raf.current), timer.current && clearTimeout(timer.current),
       inactivity.current && clearTimeout(inactivity.current)];
      raf.current = timer.current = inactivity.current = null; };
  }, [sessionId]);

  return { messages, streaming, error, reset };
}
