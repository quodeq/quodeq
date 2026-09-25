// message.role: the transcript item kind MessageList.jsx switches on to pick
// a bubble style. A different domain from vocab/frameType.js's FRAME_TYPE
// (the SSE wire frame's own type) even where a spelling coincides
// ('warning'). Kept off useAssistantStream.js so tests that fully mock that
// hook module don't also have to re-export it.
export const MESSAGE_ROLE = Object.freeze({
  USER: 'user', ASSISTANT: 'assistant', TOOL: 'tool', LOCAL: 'local', ACTION: 'action', WARNING: 'warning',
});
