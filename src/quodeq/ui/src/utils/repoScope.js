/**
 * Turn an absolute path under a project root into a repo-relative scope
 * string, or return it unchanged when it isn't actually under that root.
 *
 * The naive `path.replace(root, '')` this replaces treated `root` as a
 * substring anywhere in `path`, so a sibling folder sharing the root's name
 * as a prefix (root `/repo`, path `/repo2/x`) got mangled into `2/x` instead
 * of being left alone. Anchoring on `root + '/'` fixes that.
 *
 * @param {string} absPath
 * @param {string|null|undefined} root
 * @returns {string}
 */
export function toRepoRelativeScope(absPath, root) {
  if (!root) return absPath;
  if (absPath === root) return '';
  const prefix = root.endsWith('/') ? root : `${root}/`;
  return absPath.startsWith(prefix) ? absPath.slice(prefix.length) : absPath;
}
