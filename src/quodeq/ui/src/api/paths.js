/**
 * URL paths of the API's per-project resources, relative to the API base.
 */

/** Path of a local project's resources: `/projects/<id>`, the id URL-encoded. */
export function projectPath(projectId) {
  return `/projects/${encodeURIComponent(projectId)}`;
}

/** Query string naming the fleet of a `/fleet/compare` request, every id URL-encoded. */
export function fleetQuery(projectIds) {
  return `?projects=${projectIds.map(encodeURIComponent).join(',')}`;
}

/** Path of a shared project's resources: `/shared/projects/<id>`, the id URL-encoded. */
export function sharedProjectPath(projectId) {
  return `/shared/projects/${encodeURIComponent(projectId)}`;
}
