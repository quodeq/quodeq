/**
 * Safe clipboard write — catches and warns on failure (e.g. permissions
 * denied, insecure context, iframe sandbox).
 *
 * @param {string} text
 */
export function copyToClipboard(text) {
  navigator.clipboard.writeText(text).catch((err) =>
    console.warn('Clipboard write failed:', err)
  );
}
