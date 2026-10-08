/**
 * How the app identifies a project: by its id, or by its name when it has no
 * id. Selection state, cache keys and the backend's run lookup all key on
 * this, so every comparison against a selected project goes through here.
 */

/**
 * The key a project object is selected and looked up by.
 * @param {{id?: string|null, name?: string}} project
 * @returns {string|undefined}
 */
export function projectId(project) {
  return project.id || project.name;
}

/**
 * Like projectId, for lists that may hold bare project names as well as
 * project objects: a bare name is its own key.
 * @param {{id?: string|null, name?: string}|string} entry
 * @returns {string}
 */
export function projectIdOrSelf(entry) {
  return entry.id || entry.name || entry;
}

/**
 * The project in `projects` whose projectId is `key`, or null when there is
 * none or no list.
 * @param {Array<{id?: string|null, name?: string}>|null|undefined} projects
 * @param {string} key
 * @returns {object|null}
 */
export function findProject(projects, key) {
  return projects?.find((p) => projectId(p) === key) || null;
}

const GIT_SUFFIX = '.git';

/**
 * One canonical form for the equivalent spellings of a git remote (https,
 * ssh, scp-like `git@host:path`, userinfo, trailing `.git` or `/`), so a
 * project registered over SSH matches a CI checkout over https. Mirrors the
 * backend's `shared/repo.py:normalize_remote_url`.
 * @param {string|null|undefined} url
 * @returns {string|null} e.g. `github.com/owner/repo`, or null when blank
 */
export function normalizeOriginUrl(url) {
  let u = String(url ?? '').trim();
  if (!u) return null;
  u = u.replace(/^[a-z+]+:\/\//i, '');
  u = u.replace(/^[^@/]+@/, '');
  u = u.replace(/^([^/:]+):(?!\d)/, '$1/');
  u = u.replace(/\/+$/, '');
  if (u.toLowerCase().endsWith(GIT_SUFFIX)) u = u.slice(0, -GIT_SUFFIX.length);
  return u.toLowerCase() || null;
}
