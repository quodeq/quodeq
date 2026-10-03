import { FILE_URL_PREFIX } from '../features/onboarding/onboardingVocab.js';

// A Windows path starts with a drive letter; a file url needs a slash before it
// (`file:///C:/Users/...`) and forward slashes, the form `Path.as_uri()` writes
// and the server reads back.
const WINDOWS_DRIVE = /^[A-Za-z]:[\\/]/;
const LEADING_SLASH_DRIVE = /^\/[A-Za-z]:\//;

/**
 * The `file://` url for a folder the picker returned.
 * @param {string} path
 * @returns {string}
 */
export function fileUrlFromPath(path) {
  if (WINDOWS_DRIVE.test(path)) return `${FILE_URL_PREFIX}/${path.replace(/\\/g, '/')}`;
  return `${FILE_URL_PREFIX}${path}`;
}

/**
 * The folder a `file://` url names, as the picker would show it; '' for any other url.
 * @param {string} url
 * @returns {string}
 */
export function pathFromFileUrl(url) {
  if (!url?.startsWith(FILE_URL_PREFIX)) return '';
  const raw = url.slice(FILE_URL_PREFIX.length);
  return LEADING_SLASH_DRIVE.test(raw) ? raw.slice(1) : raw;
}
