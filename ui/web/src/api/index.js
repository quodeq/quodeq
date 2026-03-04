const BASE = import.meta.env.VITE_API_BASE || '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  const payload = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(payload.error || `Request failed: ${res.status}`);
  }

  return payload;
}

export function listProjects() {
  return request('/projects');
}

export function getProjectInfo(projectId) {
  return request(`/projects/${encodeURIComponent(projectId)}/info`);
}

export function getDashboard(projectId, run = 'latest') {
  const q = run ? `?run=${encodeURIComponent(run)}` : '';
  return request(`/projects/${encodeURIComponent(projectId)}/dashboard${q}`);
}

export function startEvaluation(input) {
  return request('/evaluations', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function getEvaluation(jobId) {
  return request(`/evaluations/${encodeURIComponent(jobId)}`);
}

export function cancelEvaluation(jobId) {
  return request(`/evaluations/${encodeURIComponent(jobId)}`, { method: 'DELETE' });
}

export function getAccumulated(projectId, asOfRun = null) {
  const q = asOfRun ? `?asOf=${encodeURIComponent(asOfRun)}` : '';
  return request(`/projects/${encodeURIComponent(projectId)}/accumulated${q}`);
}

export function getDimensionEval(projectId, runId, dimension) {
  return request(
    `/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/dimensions/${encodeURIComponent(dimension)}/eval`
  );
}

export function browseDirectory(dirPath = '') {
  const q = dirPath ? `?path=${encodeURIComponent(dirPath)}` : '';
  return request(`/browse${q}`);
}

export function getAiClients() {
  return request('/ai-clients');
}

export function getClientModels(clientId) {
  return request(`/ai-clients/${encodeURIComponent(clientId)}/models`);
}
