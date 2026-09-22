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
import { DEFAULT_PROJECT_SOURCE } from '../constants.js';

// Stand-in job/run id for queries kept mounted with `enabled: false`:
// react-query still wants a stable key, and routing the placeholder through
// the factories below keeps it in the same cache subtree as the real entries.
export const NO_JOB_ID = "_none_";

export const evaluationKeys = {
  all: () => ["evaluation"],
  evaluation: (jobId) => ["evaluation", jobId],
  status: (jobId) => ["evaluation", jobId, "status"],
  findings: (jobId) => ["evaluation", jobId, "findings"],
  dimensions: (jobId) => ["evaluation", jobId, "dimensions"],
};

// The project-key layout: ["project", projectId, source, ...subkey]. Every
// factory below and samePlaceholderScope's index reads go through these two,
// so the layout is written once.
const PROJECT_SCOPE = "project";
const PROJECT_ID_INDEX = 1;
const PROJECT_SOURCE_INDEX = 2;

/**
 * Build a project-scoped query key.
 * @param {string} projectId
 * @param {string} source 'local' | 'shared'
 * @param {...*} subkey Trailing segments identifying the query within the project subtree.
 * @returns {Array} ["project", projectId, source, ...subkey]
 */
function projectScope(projectId, source, ...subkey) {
  return [PROJECT_SCOPE, projectId, source, ...subkey];
}

export const projectKeys = {
  all: () => [PROJECT_SCOPE],
  project: (projectId, source = DEFAULT_PROJECT_SOURCE) => projectScope(projectId, source),
  scores: (projectId, asOf, source = DEFAULT_PROJECT_SOURCE) => projectScope(projectId, source, "scores", asOf || "latest"),
  dashboard: (projectId, run, source = DEFAULT_PROJECT_SOURCE) => projectScope(projectId, source, "dashboard", run || "latest"),
  runs: (projectId, source = DEFAULT_PROJECT_SOURCE) => projectScope(projectId, source, "runs"),
  info: (projectId, source = DEFAULT_PROJECT_SOURCE) => projectScope(projectId, source, "info"),
  // Explorer (dimension detail) queries. Distinct from `scores`: that one is
  // GET /projects/<p>/scores?as_of= (full payload incl. trend/availableRuns),
  // runScores is the slim GET /projects/<p>/scores/<run> used for the rescore
  // merge. Both sit inside the project subtree on purpose, so every existing
  // mutation invalidation (dismiss/delete/formula reconcile) reaches them.
  runScores: (projectId, run, source = DEFAULT_PROJECT_SOURCE) => projectScope(projectId, source, "runScores", run || "latest"),
  // Compare tab's slim per-project payload. Lives inside the project subtree
  // on purpose: dismiss/delete/formula invalidations must reach it, or the
  // fleet table would keep showing pre-dismissal scores.
  compareSummary: (projectId, source = DEFAULT_PROJECT_SOURCE) => projectScope(projectId, source, "compareSummary"),
  // Per-project enabled-standards set, fetched by Compare so every row is
  // filtered to that project's own visible dimensions (as Overview does).
  standardsVisibility: (projectId, source = DEFAULT_PROJECT_SOURCE) => projectScope(projectId, source, "standardsVisibility"),
  dimensionEval: (projectId, run, dimension, source = DEFAULT_PROJECT_SOURCE) => projectScope(projectId, source, "dimensionEval", run || "latest", dimension),
};

/**
 * placeholderData guard for project-scoped queries.
 *
 * React Query's `placeholderData: (prev) => prev` is OBSERVER-scoped, not
 * key-scoped: it hands back the last data this observer rendered no matter
 * which key produced it. That's what makes run-to-run Overview navigation feel
 * instant — but it also means switching PROJECTS leaves the previous project's
 * payload on screen, with `isLoading` false (status is 'success' on
 * placeholder data), until the new fetch lands. On a large project that is
 * several seconds of the wrong project's grades, visually indistinguishable
 * from the new project's real data.
 *
 * Gate the reuse on the key's project+source segments so a placeholder only
 * survives a change WITHIN one project's subtree (i.e. the run swap it exists
 * for), and a project or source switch falls through to a real loading state.
 *
 *   placeholderData: (prev, prevQuery) =>
 *     samePlaceholderScope(prevQuery, projectId, source) ? prev : undefined
 *
 * Reads the project/source segments through the same index constants the
 * factories above build with, so the layout is defined in one place.
 */
export function samePlaceholderScope(previousQuery, projectId, source = DEFAULT_PROJECT_SOURCE) {
  const key = previousQuery?.queryKey;
  if (!Array.isArray(key)) return false;
  return key[PROJECT_ID_INDEX] === projectId && key[PROJECT_SOURCE_INDEX] === source;
}

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
  clientModels: (clientId) => ["settings", "clientModels", clientId],
  knownModels: (providerId) => ["settings", "knownModels", providerId],
  ollamaModels: () => ["settings", "ollamaModels"],
  llamacppModels: () => ["settings", "llamacppModels"],
  omlxModels: () => ["settings", "omlxModels"],
};

export const sharedKeys = {
  all: () => ["shared"],
  status: () => ["shared", "status"],
  list: () => ["shared", "list"],
};
