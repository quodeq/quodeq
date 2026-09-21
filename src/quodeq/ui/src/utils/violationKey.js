/**
 * The identity of a finding across a rescore.
 *
 * A dismiss or a formula change returns a fresh violation list, and the UI
 * has to tell which entries survived. There is no server-side id, so the
 * req/file/line triple is the key — spelled once here because the writer
 * (applyMutationDelta) and the reader (the explorer's rescore merge) must
 * agree exactly or every finding looks new.
 */

/**
 * The req|file|line key for a violation, with each missing part defaulted so
 * two equivalent findings always produce the same string.
 *
 * @param {{req?: string, file?: string, line?: number}} [v]
 * @returns {string}
 */
export function violationKey(v) {
  return `${v?.req || ''}|${v?.file || ''}|${v?.line || 0}`;
}
