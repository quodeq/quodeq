/**
 * Typed query-key factories.
 *
 * Convention: [scope, id, ...subkey]. Pass the scope-prefix to
 * queryClient.invalidateQueries() to refetch the whole subtree.
 *
 *   evaluationKeys.evaluation('job-1')   // ['evaluation', 'job-1']         (subtree)
 *   evaluationKeys.status('job-1')       // ['evaluation', 'job-1', 'status']
 *   projectKeys.project('p1')            // ['project', 'p1', 'local']      (subtree)
 *   projectKeys.scores('p1', 'r1')       // ['project', 'p1', 'local', 'scores', 'r1']
 *   systemKeys.health()                  // ['system', 'health']
 *
 * projectKeys.* take a trailing `source` ('local' | 'shared', defaults to
 * 'local') so a project the user has pulled locally never collides in cache
 * with its shared-repo mirror of the same projectId — switching sources
 * always misses the other source's cache instead of serving stale data.
 * The source segment sits right after projectId, so `project(projectId)`
 * (no source) still prefix-matches every subkey for the *local* source only;
 * pass the caller's source explicitly if it should also match shared entries.
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
  project: (projectId, source = "local") => ["project", projectId, source],
  scores: (projectId, asOf, source = "local") => ["project", projectId, source, "scores", asOf || "latest"],
  dashboard: (projectId, run, source = "local") => ["project", projectId, source, "dashboard", run || "latest"],
  runs: (projectId, source = "local") => ["project", projectId, source, "runs"],
};

export const systemKeys = {
  all: () => ["system"],
  health: () => ["system", "health"],
  ollama: () => ["system", "ollama"],
  llamacpp: () => ["system", "llamacpp"],
  omlx: () => ["system", "omlx"],
};

export const standardsKeys = {
  all: () => ["standards"],
  list: () => ["standards", "list"],
  library: () => ["standards", "library"],
  cwes: () => ["standards", "cwes"],
  overrides: (projectId) => ["standards", "overrides", projectId],
};

export const settingsKeys = {
  all: () => ["settings"],
  aiClients: () => ["settings", "aiClients"],
  knownModels: (providerId) => ["settings", "knownModels", providerId],
  ollamaModels: () => ["settings", "ollamaModels"],
  llamacppModels: () => ["settings", "llamacppModels"],
  omlxModels: () => ["settings", "omlxModels"],
};

export const sharedKeys = {
  all: () => ["shared"],
  status: () => ["shared", "status"],
};
