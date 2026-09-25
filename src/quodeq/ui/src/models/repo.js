/**
 * Repo-string classification for the evaluation form's local/remote branch.
 *
 * Extracted from EvaluationForm.jsx. Deliberately NOT aligned with the
 * backend's shared/_repo.py is_repo_url -- the two intentionally disagree
 * on schemeless pastes (e.g. a bare "org/repo"); unifying them would change
 * registration behavior, which is a different (and much bigger) change than
 * this extraction.
 */

/**
 * Classify a repo string as 'local' or 'remote', or null for an empty value.
 *
 * Anchored: a schemeless paste like "github.com/org/repo" is remote, but a
 * local folder whose path merely contains "github.com" is not.
 */
// Repo-string classification result. Coincidentally spelled like
// vocab/projectSource.js's PROJECT_SOURCE, but a different domain: that one
// is where a project's *data* lives, this is what kind of string the
// evaluation form's repo field holds.
const REPO_LOCAL = 'local';
const REPO_REMOTE = 'remote';

export function classifyRepo(repo) {
  if (!repo) return null;
  const isRemote = repo.startsWith('http') || repo.startsWith('git@') || /^(www\.)?github\.com\//i.test(repo);
  return isRemote ? REPO_REMOTE : REPO_LOCAL;
}

export function isLocalRepo(repo) {
  return classifyRepo(repo) === REPO_LOCAL;
}
