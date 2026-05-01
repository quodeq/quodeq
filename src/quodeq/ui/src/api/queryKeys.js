/**
 * Typed query-key factories.
 *
 * Convention: [scope, id, ...subkey]. Pass the scope-prefix to
 * queryClient.invalidateQueries() to refetch the whole subtree.
 *
 *   evaluationKeys.evaluation('job-1')   // ['evaluation', 'job-1']         (subtree)
 *   evaluationKeys.status('job-1')       // ['evaluation', 'job-1', 'status']
 *   projectKeys.project('p1')            // ['project', 'p1']               (subtree)
 *   projectKeys.scores('p1', 'r1')       // ['project', 'p1', 'scores', 'r1']
 *   systemKeys.health()                  // ['system', 'health']
 */
export const evaluationKeys = {
  all: () => ["evaluation"],
  evaluation: (jobId) => ["evaluation", jobId],
  status: (jobId) => ["evaluation", jobId, "status"],
  findings: (jobId) => ["evaluation", jobId, "findings"],
  dimensions: (jobId) => ["evaluation", jobId, "dimensions"],
};

export const projectKeys = {
  all: () => ["project"],
  project: (projectId) => ["project", projectId],
  scores: (projectId, asOf) => ["project", projectId, "scores", asOf || "latest"],
  dashboard: (projectId, run) => ["project", projectId, "dashboard", run || "latest"],
  runs: (projectId) => ["project", projectId, "runs"],
};

export const systemKeys = {
  all: () => ["system"],
  health: () => ["system", "health"],
  ollama: () => ["system", "ollama"],
};
