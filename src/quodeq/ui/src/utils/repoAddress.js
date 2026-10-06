// A scheme (https://, ssh://, file://), an scp-style git@host:path, or a
// user@host:path.
const SCHEMED_OR_SCP = /^(?:[a-z][a-z0-9+.-]*:\/\/|git@|[\w.-]+@[\w.-]+:)/i;

// A host with no scheme, as people paste it from a browser bar:
// github.com/org/repo. The first segment is a dotted host name (letters,
// digits and hyphens, so it never starts with /, ., ~ or a drive letter),
// an optional port, then a path; no whitespace anywhere.
const SCHEMELESS_HOST = /^[a-z0-9-]+(?:\.[a-z0-9-]+)+(?::\d+)?\/\S+$/i;

/**
 * Whether a typed repository address reads as a git url rather than a path
 * on this machine. A host without a scheme counts: send it through
 * normalizeUrlAddress, since the server only accepts schemed or scp-style
 * urls.
 * @param {string} value
 * @returns {boolean}
 */
export function isUrlAddress(value) {
  const trimmed = (value || '').trim();
  return SCHEMED_OR_SCP.test(trimmed) || SCHEMELESS_HOST.test(trimmed);
}

/**
 * The address as the server takes it: a host without a scheme gains
 * `https://` (the server refuses plain http), anything else is only trimmed.
 * @param {string} value
 * @returns {string}
 */
export function normalizeUrlAddress(value) {
  const trimmed = (value || '').trim();
  return !SCHEMED_OR_SCP.test(trimmed) && SCHEMELESS_HOST.test(trimmed) ? `https://${trimmed}` : trimmed;
}
