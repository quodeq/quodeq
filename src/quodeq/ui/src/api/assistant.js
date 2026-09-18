import { request, BASE } from './request.js';

/**
 * Opens an assistant session for the given project/workspace payload.
 * The returned session id keys every other call in this module.
 */
export function createAssistantSession(payload) {
  return request('/assistant/sessions', { method: 'POST', body: JSON.stringify(payload) });
}

/**
 * Sends one user turn to an open session. The assistant's reply arrives on
 * the event stream (see assistantEventsUrl), not in this response.
 */
export function postAssistantMessage(sessionId, body) {
  return request(`/assistant/sessions/${encodeURIComponent(sessionId)}/messages`,
    { method: 'POST', body: JSON.stringify(body) });
}

/**
 * Interrupts the turn currently running in the session.
 */
export function stopAssistantTurn(sessionId) {
  return request(`/assistant/sessions/${encodeURIComponent(sessionId)}/stop`,
    { method: 'POST' });
}

/**
 * Accepts a proposed action, letting the backend perform it.
 */
export function applyAssistantAction(actionId) {
  return request(`/assistant/actions/${encodeURIComponent(actionId)}/apply`, { method: 'POST' });
}

/**
 * Declines a proposed action so the backend drops it.
 */
export function rejectAssistantAction(actionId) {
  return request(`/assistant/actions/${encodeURIComponent(actionId)}/reject`, { method: 'POST' });
}

/**
 * The session's SSE endpoint. `afterSeq` resumes the stream after the last
 * sequence number the client already received, so a reconnect replays only
 * the gap.
 *
 * @returns {string}
 */
export function assistantEventsUrl(sessionId, afterSeq = 0) {
  return `${BASE}/assistant/sessions/${encodeURIComponent(sessionId)}/events?after=${afterSeq}`;
}

/**
 * The skills the backend can offer, for the command menu.
 */
export function fetchAssistantCatalog() {
  return request('/assistant/skills');
}

/**
 * The session's workspace state (the branch the assistant is editing).
 */
export function fetchAssistantWorkspace(sessionId) {
  return request(`/assistant/sessions/${encodeURIComponent(sessionId)}/workspace`);
}

/**
 * The diff of everything the session has changed in its workspace.
 */
export function fetchAssistantWorkspaceDiff(sessionId) {
  return request(`/assistant/sessions/${encodeURIComponent(sessionId)}/workspace/diff`);
}

// Mutations run git push + gh, each up to ~120s, so they use a longer client
// timeout than the 30s default to avoid falsely reporting a failure mid-flight.
const WORKSPACE_MUTATION_TIMEOUT_MS = 300000;

/**
 * Lands the session's workspace changes.
 */
export function applyAssistantWorkspace(sessionId) {
  return request(`/assistant/sessions/${encodeURIComponent(sessionId)}/workspace/apply`,
    { method: 'POST', timeout: WORKSPACE_MUTATION_TIMEOUT_MS });
}

/**
 * Opens a pull request from the session's workspace branch.
 */
export function createAssistantWorkspacePr(sessionId, body) {
  return request(`/assistant/sessions/${encodeURIComponent(sessionId)}/workspace/pr`,
    { method: 'POST', body: JSON.stringify(body), timeout: WORKSPACE_MUTATION_TIMEOUT_MS });
}

/**
 * Throws away the session's workspace changes.
 */
export function discardAssistantWorkspace(sessionId) {
  return request(`/assistant/sessions/${encodeURIComponent(sessionId)}/workspace/discard`,
    { method: 'POST', timeout: WORKSPACE_MUTATION_TIMEOUT_MS });
}
