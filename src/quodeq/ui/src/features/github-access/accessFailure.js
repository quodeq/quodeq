import { isAccessCode } from '../../strings/apiErrors.js';

/**
 * The access panel's `failure` envelope from a rejected clone or connect, or
 * null when the rejection is not a pre-clone probe verdict (ACCESS_<KIND>).
 * @param {unknown} err - the rejected error from the api layer
 * @returns {{kind: string|undefined, detail: string, host: string, isGitHub: boolean, cloneUrl: string}|null}
 */
export function accessFailureFrom(err) {
  if (!isAccessCode(err?.code)) return null;
  const body = err.body || {};
  return {
    kind: body.kind, detail: body.detail || '', host: body.host || '', isGitHub: Boolean(body.isGitHub), cloneUrl: body.cloneUrl || '',
  };
}
