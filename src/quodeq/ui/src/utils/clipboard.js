/**
 * Safe clipboard write — catches and warns on failure (e.g. permissions
 * denied, insecure context, iframe sandbox, API unavailable). Never rejects:
 * resolves `true` on success, `false` on failure, so callers can gate
 * success-only UI (e.g. a "Copied" indicator) on the resolved value instead
 * of assuming the write always worked.
 *
 * @param {string} text
 * @returns {Promise<boolean>}
 */
export function copyToClipboard(text) {
  if (!navigator.clipboard?.writeText) return Promise.resolve(false);
  return navigator.clipboard.writeText(text).then(
    () => true,
    (err) => {
      console.warn('Clipboard write failed:', err);
      return false;
    },
  );
}
