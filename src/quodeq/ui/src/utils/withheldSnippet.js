/**
 * A finding pulled from a shared repository whose publisher did not share
 * code carries a token in place of its snippet: the finding's fingerprint
 * behind this prefix (core/finding_identity.py's WITHHELD_SNIPPET_PREFIX), so
 * dismissals still match it. It is never code to show or copy.
 */
const WITHHELD_SNIPPET_PREFIX = 'quodeq:snippet-withheld:';

/** True when `snippet` is the token a publisher left in place of the code. */
export function isWithheldSnippet(snippet) {
  return typeof snippet === 'string' && snippet.startsWith(WITHHELD_SNIPPET_PREFIX);
}

/** The snippet as code to show, or '' when there is none or it was withheld. */
export function shownSnippet(snippet) {
  return isWithheldSnippet(snippet) ? '' : (snippet || '');
}
