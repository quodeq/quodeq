/**
 * GitHub access: the pre-clone probe, the stored account, the device flow and
 * the paste-a-token path (api/routes_github_access.py).
 */
import { request } from './request.js';

// One probe is 15 s server-side and the ladder may run three; stay above that.
const PROBE_TIMEOUT_MS = 60000;

/** @returns {Promise<{reachable: boolean, method: string, kind: string, detail: string, host: string, isGitHub: boolean, cloneUrl: string|null}>} */
export function probeGit(url) {
  return request('/git/probe', { method: 'POST', body: JSON.stringify({ url }), timeout: PROBE_TIMEOUT_MS });
}

/** @returns {Promise<{signedIn: boolean, login: string|null, method: string, expiresAt: number|null, ghAvailable: boolean, ghLoggedIn: boolean}>} */
export function getGithubAccount() {
  return request('/github/account');
}

/** @returns {Promise<{userCode: string, verificationUri: string, expiresIn: number, interval: number}>} */
export function startDeviceFlow() {
  return request('/github/device-flow', { method: 'POST' });
}

/** @returns {Promise<{state: string, login: string|null, error: string|null, code: string|null, userCode: string|null, verificationUri: string|null}>} */
export function getDeviceFlow() {
  return request('/github/device-flow');
}

/** @returns {Promise<{login: string}>} */
export function pasteGithubToken(token) {
  return request('/github/token', { method: 'POST', body: JSON.stringify({ token }) });
}

/** Forget the stored GitHub token. The 204 carries no body. */
export async function signOutGithub() {
  await request('/github/account', { method: 'DELETE' });
}
