/**
 * The project clone job's slot. POST /projects with a git URL answers 202 and
 * the clone runs in the background; progress and the outcome live here.
 */

import { request } from './request.js';
import { normalizeSlot } from './sharedStatus.js';
import { isSlotActive } from './syncStatus.js';

const REPO_FALLBACK_NAME = 'repo';
const GIT_SUFFIX = /\.git$/;
const PATH_SEPARATORS = /[/:]/;

/** The clone slot's code for a repo the server already holds; `detail` is its id. */
export const CLONE_CODE_PROJECT_EXISTS = 'PROJECT_EXISTS';

/** @returns {Promise<Object>} the clone slot, finishedAt in epoch ms */
export async function getCloneStatus() {
  return normalizeSlot(await request('/projects/clone-status'));
}

/**
 * Whether the clone job is still working (DONE and ERROR are terminal).
 * @param {Object|null|undefined} slot
 * @returns {boolean}
 */
export function isCloneActive(slot) { return isSlotActive(slot); }

/**
 * Last path segment of a git URL without `.git`; "repo" when there is none.
 * @param {string} url
 * @returns {string}
 */
export function cloneNameFromUrl(url) {
  const last = String(url || '').split(PATH_SEPARATORS).at(-1).replace(GIT_SUFFIX, '');
  return last || REPO_FALLBACK_NAME;
}
