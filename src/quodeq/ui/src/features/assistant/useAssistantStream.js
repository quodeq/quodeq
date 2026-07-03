import { useCallback, useEffect, useRef, useState } from 'react';
import { assistantEventsUrl } from '../../api/assistant.js';

const INACTIVITY_MS = 60000;

export function useAssistantStream(sessionId, { onDone } = {}) {
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const pending = useRef(''); const raf = useRef(null); const timer = useRef(null);
  const inactivity = useRef(null); const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  const reset = useCallback(() => { setMessages([]); setError(null); }, []);

  useEffect(() => {
    if (!sessionId) { setStreaming(false); return undefined; }
    setMessages([]); setError(null); setStreaming(true); pending.current = '';

    const flushTokens = () => {
      if (raf.current != null) { cancelAnimationFrame(raf.current); raf.current = null; }
      if (timer.current != null) { clearTimeout(timer.current); timer.current = null; }
      const chunk = pending.current; if (!chunk) return;
      pending.current = '';
      setMessages((prev) => {
        const next = prev.slice();
        const last = next[next.length - 1];
        if (last && last.role === 'assistant') next[next.length - 1] = { ...last, text: last.text + chunk };
        else next.push({ role: 'assistant', text: chunk });
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
    const finish = () => { if (inactivity.current) clearTimeout(inactivity.current);
      flushTokens(); setStreaming(false); es.close(); onDoneRef.current?.(); };

    es.onmessage = (e) => {
      resetInactivity();
      let frame; try { frame = JSON.parse(e.data); } catch { return; }
      if (frame.type === 'token') { pending.current += frame.text || ''; scheduleFlush(); }
      else if (frame.type === 'tool_call') { flushTokens(); append({ role: 'tool', name: frame.name }); }
      else if (frame.type === 'action_draft') { flushTokens();
        append({ role: 'action', actionId: frame.actionId, actionType: frame.actionType, summary: frame.summary }); }
      else if (frame.type === 'warning') { flushTokens(); append({ role: 'warning', message: frame.message }); }
      else if (frame.type === 'error') { flushTokens(); setError(frame.message || 'error'); finish(); }
      else if (frame.type === 'done') { finish(); }
      else if (frame.type === 'heartbeat') { /* liveness only: resetInactivity() already ran above */ }
    };
    es.addEventListener('done', finish);
    es.onerror = () => { if (es.readyState === 2) { setStreaming(false); setError((p) => p || 'disconnected'); } };
    resetInactivity();

    return () => { es.close();
      [raf.current && cancelAnimationFrame(raf.current), timer.current && clearTimeout(timer.current),
       inactivity.current && clearTimeout(inactivity.current)];
      raf.current = timer.current = inactivity.current = null; };
  }, [sessionId]);

  return { messages, streaming, error, reset };
}
