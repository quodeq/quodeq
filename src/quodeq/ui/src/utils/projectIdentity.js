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
