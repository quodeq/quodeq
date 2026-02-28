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

export function getProjectInfo(project) {
  return request(`/projects/${encodeURIComponent(project)}/info`);
}

export function getDashboard(project, run = 'latest') {
  const q = run ? `?run=${encodeURIComponent(run)}` : '';
  return request(`/projects/${encodeURIComponent(project)}/dashboard${q}`);
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

export function getAccumulated(project, asOfRun = null) {
  const q = asOfRun ? `?asOf=${encodeURIComponent(asOfRun)}` : '';
  return request(`/projects/${encodeURIComponent(project)}/accumulated${q}`);
}

export function getDimensionEval(project, runId, dimension) {
  return request(
    `/projects/${encodeURIComponent(project)}/runs/${encodeURIComponent(runId)}/dimensions/${encodeURIComponent(dimension)}/eval`
  );
}

export function browseDirectory(dirPath = '') {
  const q = dirPath ? `?path=${encodeURIComponent(dirPath)}` : '';
  return request(`/browse${q}`);
}
