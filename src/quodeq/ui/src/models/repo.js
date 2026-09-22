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
export function classifyRepo(repo) {
  if (!repo) return null;
  const isRemote = repo.startsWith('http') || repo.startsWith('git@') || /^(www\.)?github\.com\//i.test(repo);
  return isRemote ? 'remote' : 'local';
}

export function isLocalRepo(repo) {
  return classifyRepo(repo) === 'local';
}
