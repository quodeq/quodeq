// Mirror of src/quodeq/assistant/frame_type.py:FrameType, the assistant SSE
// frame's `type`. A different domain from the run/job/dim vocabularies even
// where a spelling coincides ('error', 'done').
export const FRAME_TYPE = Object.freeze({
  TOKEN: 'token', TOOL_CALL: 'tool_call', ACTION_DRAFT: 'action_draft',
  WARNING: 'warning', ERROR: 'error', STOPPED: 'stopped', DONE: 'done', HEARTBEAT: 'heartbeat',
});
