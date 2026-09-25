/**
 * URL paths of the API's per-project resources, relative to the API base.
 */

/** Path of a local project's resources: `/projects/<id>`, the id URL-encoded. */
export function projectPath(projectId) {
  return `/projects/${encodeURIComponent(projectId)}`;
}

/** Path of a shared project's resources: `/shared/projects/<id>`, the id URL-encoded. */
export function sharedProjectPath(projectId) {
  return `/shared/projects/${encodeURIComponent(projectId)}`;
}
