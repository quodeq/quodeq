import { request, BASE } from './request.js';

export function createAssistantSession(payload) {
  return request('/assistant/sessions', { method: 'POST', body: JSON.stringify(payload) });
}

export function postAssistantMessage(sessionId, body) {
  return request(`/assistant/sessions/${encodeURIComponent(sessionId)}/messages`,
    { method: 'POST', body: JSON.stringify(body) });
}

export function applyAssistantAction(actionId) {
  return request(`/assistant/actions/${encodeURIComponent(actionId)}/apply`, { method: 'POST' });
}

export function rejectAssistantAction(actionId) {
  return request(`/assistant/actions/${encodeURIComponent(actionId)}/reject`, { method: 'POST' });
}

export function assistantEventsUrl(sessionId, afterSeq = 0) {
  return `${BASE}/assistant/sessions/${encodeURIComponent(sessionId)}/events?after=${afterSeq}`;
}

export function fetchAssistantCatalog() {
  return request('/assistant/skills');
}
