// A url as a key: scheme and case aside, with no trailing slash or .git.
function repoKey(url) {
  return (url || '').trim().replace(/^[a-z][a-z0-9+.-]*:\/\//i, '').replace(/\/+$/, '').replace(/\.git$/i, '').toLowerCase();
}

function baseName(path) {
  return (path || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop() || '';
}

/**
 * Whether a listed local project is the one a running clone slot is still
 * bringing in. The record is written while git works, so the list can hold
 * the project before its folder exists; the Repositories tab hides its card
 * behind the tile and the app keeps Evaluate away from it until it lands.
 * The record's path is resolved and the slot's is not, so a symlinked root
 * defeats a plain path match: the origin url and the folder name count too.
 * @param {{ id?: string, path?: string, originUrl?: string }|null|undefined} local
 * @param {{ projectId?: string, repo?: string, dest?: string }|null|undefined} slot - an ACTIVE clone slot
 * @returns {boolean}
 */
export function isCloningProject(local, slot) {
  if (!local || !slot) return false;
  if (slot.projectId && local.id === slot.projectId) return true;
  if (slot.repo && local.originUrl && repoKey(local.originUrl) === repoKey(slot.repo)) return true;
  return Boolean(slot.dest) && (local.path === slot.dest || baseName(local.path) === baseName(slot.dest));
}
