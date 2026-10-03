// SSE log-stream lifecycle shared by every panel that tails a server log over
// EventSource: the eval-log job stream (eval-log/useJobLogStream.js) and the
// local-provider server logs (settings/hooks/useProviderLogStream.js). No
// Python mirror: the stream is UI-only, so this lives in vocab/ as a
// UI-only exception (see tests/tools/test_vocab_mirrors_match_ui.py).
export const LOG_STREAM_STATUS = Object.freeze({
  IDLE: 'idle', STREAMING: 'streaming', DONE: 'done', ERROR: 'error',
});
