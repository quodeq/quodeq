import { useCallback, useEffect, useRef, useState } from 'react';
import FolderBrowser from '../../evaluation/components/FolderBrowser.jsx';
import { t } from '../../../strings/index.js';

/**
 * The folder browser as a promise, for forms that take an injected
 * `browseFolder` (EvaluationsRepoForm). `browseFolder()` opens the modal and
 * resolves with the chosen path on confirm, or null when it is closed;
 * `picker` is the modal element to render while it is open (null otherwise).
 * The pending resolver lives in a ref so a re-render never drops it, and an
 * unmount mid-pick settles it with null.
 *
 * @param {{ title?: string }} [options]
 * @returns {{ browseFolder: () => Promise<string|null>, picker: JSX.Element|null }}
 */
export function useFolderPicker({ title = t('onboarding.folderPickerTitle') } = {}) {
  const [open, setOpen] = useState(false);
  const resolverRef = useRef(null);

  const settle = useCallback((path) => {
    const resolve = resolverRef.current;
    resolverRef.current = null;
    setOpen(false);
    resolve?.(path);
  }, []);

  const browseFolder = useCallback(() => new Promise((resolve) => {
    resolverRef.current?.(null); // a second open supersedes the first
    resolverRef.current = resolve;
    setOpen(true);
  }), []);

  useEffect(() => () => { resolverRef.current?.(null); }, []);

  const picker = open
    ? <FolderBrowser title={title} onSelect={(path) => settle(path)} onClose={() => settle(null)} />
    : null;
  return { browseFolder, picker };
}
