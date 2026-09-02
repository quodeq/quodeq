import { useCallback, useEffect, useRef, useState } from 'react';
import { assistantEventsUrl } from '../../api/assistant.js';
import { t } from '../../strings/index.js';

const INACTIVITY_MS = 60000;
// Max characters revealed per flush tick. Delta-streaming providers (ollama,
// claude) send frames smaller than this, so they render unchanged; providers
// without deltas (codex) deliver a whole message as ONE frame, which sweeps
// in at a readable rate instead of popping as a block.
const CHARS_PER_TICK = 60;

/**
 * Pure frame-dispatch table: given a parsed SSE frame and the effect's
 * (already-bound) per-type handlers, calls the one matching frame.type.
 * Extracted verbatim from useAssistantStream's `es.onmessage` handler —
 * partial extraction only, per the split's scope; the rest of the effect
 * (scheduling, refs, EventSource wiring) stays inline.
 */
export function applyFrame(frame, handlers) {
  if (!frame || typeof frame !== 'object') return;
  const { onToken, onToolCall, onActionDraft, onWarning, onError, onStopped, onDone, onHeartbeat } = handlers;
  if (frame.type === 'token') onToken(frame);
  else if (frame.type === 'tool_call') onToolCall(frame);
  else if (frame.type === 'action_draft') onActionDraft(frame);
  else if (frame.type === 'warning') onWarning(frame);
  else if (frame.type === 'error') onError(frame);
  // User-initiated stop: terminal like done (turn over, stream stays
  // open), plus a visible marker so the truncated answer isn't mistaken
  // for a complete one.
  else if (frame.type === 'stopped') onStopped(frame);
  else if (frame.type === 'done') onDone(frame);
  else if (frame.type === 'heartbeat') onHeartbeat?.(frame); // liveness only: resetInactivity() already ran by the caller
}

export function useAssistantStream(sessionId, { onDone } = {}) {
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const pending = useRef(''); const raf = useRef(null); const timer = useRef(null);
  const inactivity = useRef(null); const onDoneRef = useRef(onDone);
  // Set when the turn's `done` arrived while text was still being revealed:
  // the turn ends when the drain empties instead of force-flushing the rest.
  const endPending = useRef(false);
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
    turnBoundary.current = false; endPending.current = false;

    const finishTurn = () => { endPending.current = false; setStreaming(false);
      turnBoundary.current = true; onDoneRef.current?.(); };
    const drain = (all) => {
      if (raf.current != null) { cancelAnimationFrame(raf.current); raf.current = null; }
      if (timer.current != null) { clearTimeout(timer.current); timer.current = null; }
      const buf = pending.current;
      if (!buf) { if (endPending.current) finishTurn(); return; }
      const chunk = all ? buf : buf.slice(0, CHARS_PER_TICK);
      pending.current = all ? '' : buf.slice(CHARS_PER_TICK);
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
      if (pending.current) scheduleFlush();
      else if (endPending.current) finishTurn();
    };
    // Structural frames (tool calls, warnings, errors, stop) force the rest
    // of the reveal out at once so ordering stays exact and errors are never
    // delayed behind an animation.
    const flushTokens = () => drain(true);
    const scheduleFlush = () => {
      if (raf.current == null) raf.current = requestAnimationFrame(() => drain(false));
      if (timer.current == null) timer.current = setTimeout(() => drain(false), 50);
    };
    const append = (msg) => setMessages((prev) => [...prev, msg]);
    const es = new EventSource(assistantEventsUrl(sessionId, 0));
    // End the TURN (clear spinner, mark a boundary, notify the provider)
    // WITHOUT closing the connection — the stream stays open so the next
    // turn's frames still arrive. The EventSource is only closed in the
    // effect cleanup (sessionId change / unmount). If text is still being
    // revealed, the turn ends when the drain empties.
    const endTurn = () => {
      if (pending.current) { endPending.current = true; scheduleFlush(); }
      else finishTurn();
    };
    const resetInactivity = () => {
      if (inactivity.current) clearTimeout(inactivity.current);
      // End the turn cleanly (same as any other terminal frame) instead of
      // closing the stream: closing here would leave the provider's
      // turnActive stuck true forever (endTurn never ran) AND kill the
      // EventSource with nothing left to reconnect it, wedging the drawer.
      // Leaving the connection open lets the next turn (or a heartbeat)
      // recover it.
      inactivity.current = setTimeout(() => { setError(t('assistant.streamTimedOut')); endTurn(); }, INACTIVITY_MS);
    };
    // First content frame of a turn: re-arm streaming and, once a turn
    // boundary has been crossed, clear any stale stream error from the prior
    // turn so a retry starts clean.
    const beginContent = () => { if (turnBoundary.current) setError(null); setStreaming(true); };

    es.onmessage = (e) => {
      resetInactivity();
      let frame; try { frame = JSON.parse(e.data); } catch { return; }
      applyFrame(frame, {
        onToken: (f) => {
          // A next-turn token during the previous turn's reveal: close that
          // turn out first so the new text starts its own bubble.
          if (endPending.current) drain(true);
          beginContent(); pending.current += f.text || ''; scheduleFlush();
        },
        onToolCall: (f) => { beginContent(); flushTokens(); append({ role: 'tool', name: f.name, argsSummary: f.argsSummary }); },
        onActionDraft: (f) => { beginContent(); flushTokens();
          append({ role: 'action', actionId: f.actionId, actionType: f.actionType, summary: f.summary }); },
        onWarning: (f) => { beginContent(); flushTokens(); append({ role: 'warning', message: f.message }); },
        onError: (f) => { flushTokens(); setError(f.message || 'error'); endTurn(); },
        onStopped: () => { flushTokens(); append({ role: 'warning', message: 'Stopped.' }); endTurn(); },
        onDone: () => { endTurn(); },
      });
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
