import { useState } from 'react';
import { readString, writeString, removeKey } from '../../../adapters/storage.js';
import { LAST_CLONE_ROOT_STORAGE_KEY } from '../../../constants.js';
import { useFolderPicker } from '../../dashboard/hooks/useFolderPicker.jsx';
import { t } from '../../../strings/index.js';

// Where the server clones a url when the request names no cloneDest. Shown,
// never sent: only a root the user picked travels as cloneDest.
export const DEFAULT_WORKING_COPY_ROOT = '~/quodeq/repos';

// The folder a clone lands in: the url's last path segment without `.git`
// (https://host/org/billing.git and git@host:org/billing both give billing).
function repoName(url) {
  const trimmed = (url || '').trim().replace(/\/+$/, '').replace(/\.git$/i, '');
  return trimmed.split(/[/:]/).pop() || '';
}

/**
 * The working copy of a pasted url: the root folder (the remembered pick, else
 * the default), the repository's folder name under it, and `change`/`reset`.
 * A picked root is remembered under LAST_CLONE_ROOT_STORAGE_KEY; `cloneDest`
 * is that root, or undefined while the default applies.
 *
 * @param {string} repo - the pasted url
 */
export function useWorkingCopy(repo) {
  const [root, setRoot] = useState(() => readString(LAST_CLONE_ROOT_STORAGE_KEY) || DEFAULT_WORKING_COPY_ROOT);
  const { browseFolder, picker } = useFolderPicker({ title: t('onboarding.workingCopyPickerTitle') });
  const name = repoName(repo);
  const changed = root !== DEFAULT_WORKING_COPY_ROOT;

  const change = async () => {
    const picked = await browseFolder();
    if (!picked) return;
    setRoot(picked);
    if (!writeString(LAST_CLONE_ROOT_STORAGE_KEY, picked)) console.warn('[useWorkingCopy] could not persist the working-copy root'); // private mode
  };
  const reset = () => {
    setRoot(DEFAULT_WORKING_COPY_ROOT);
    removeKey(LAST_CLONE_ROOT_STORAGE_KEY);
  };

  return {
    root, name, path: name ? `${root}/${name}` : root, changed,
    cloneDest: changed ? root : undefined,
    change, reset, picker,
  };
}
