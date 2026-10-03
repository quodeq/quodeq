// Named SSE events the run and job-log streams send. Mirrors
// src/quodeq/api/sse_frames.py:HEARTBEAT_EVENT and the event names in
// _run_event_stream.py. A heartbeat is a data event, not an SSE comment:
// comments never reach EventSource listeners, so only a real event can keep
// the client's inactivity timer from tripping on a quiet run.
export const SSE_EVENT = Object.freeze({
  STATUS: 'status',
  DIMENSION_COMPLETED: 'dimension-completed',
  FINDING: 'finding',
  DONE: 'done',
  HEARTBEAT: 'heartbeat',
});
