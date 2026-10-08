/**
 * Reading a run this app did not start (the nightly, a PR review, a
 * terminal or MCP run) from the data that exists today: the job's source,
 * its git origin and commit, and the per-dimension progress.
 */
import { normalizeOriginUrl } from '../../utils/projectIdentity.js';
import { JOB_SOURCE } from '../../vocab/jobStatus.js';

/** Characters of a commit sha shown in the identity strip and details. */
export const SHORT_SHA = 7;

const DIFF_REASON = 'diff';
const GITHUB_HOST = 'github.com/';
const SHA_RE = /^[0-9a-f]{7,40}$/i;

function dims(progress) {
  return Array.isArray(progress?.dimensions) ? progress.dimensions : [];
}

/**
 * True for a run the app did not start.
 * @param {object|null} job
 * @returns {boolean}
 */
export function isExternal(job) {
  return job?.source === JOB_SOURCE.EXTERNAL;
}

/**
 * True when the run only reviews a diff (a PR review): its dimensions were
 * estimated from the changed files.
 * @param {object|null} progress the /progress payload
 * @returns {boolean}
 */
export function isDiffReview(progress) {
  return dims(progress).some((d) => d?.estimateReason === DIFF_REASON);
}

/**
 * Files in the reviewed diff: the widest diff dimension's file total.
 * @param {object|null} progress
 * @returns {number|null} null when the run is not a diff review
 */
export function diffFileCount(progress) {
  const totals = dims(progress)
    .filter((d) => d?.estimateReason === DIFF_REASON)
    .map((d) => d?.files?.total)
    .filter((n) => typeof n === 'number');
  return totals.length ? Math.max(...totals) : null;
}

/**
 * Checks that passed so far, summed over dimensions.
 * @param {object|null} progress
 * @returns {number}
 */
export function checksPassed(progress) {
  return dims(progress).reduce((n, d) => n + (typeof d?.compliance === 'number' ? d.compliance : 0), 0);
}

/**
 * The commit's page on GitHub, for a github.com origin and a real sha.
 * @param {string|null} originUrl
 * @param {string|null} sha
 * @returns {string|null}
 */
export function githubCommitUrl(originUrl, sha) {
  const repo = normalizeOriginUrl(originUrl);
  if (!repo || !repo.startsWith(GITHUB_HOST) || !SHA_RE.test(sha ?? '')) return null;
  return `https://${repo}/commit/${sha}`;
}
