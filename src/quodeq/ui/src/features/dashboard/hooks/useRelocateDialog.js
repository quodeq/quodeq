import { useState } from 'react';
import { t } from '../../../strings/index.js';

/**
 * The inline relocate editor under a row whose folder is missing: which
 * project is being relocated, the typed path, and a validation message.
 *
 * @param {(name: string, path: string) => void} onRelocate
 */
export function useRelocateDialog(onRelocate) {
  const [relocating, setRelocating] = useState(null);
  const [relocatePath, setRelocatePath] = useState('');
  const [relocateError, setRelocateError] = useState(null);
  const startRelocate = (name, currentPath) => {
    setRelocating(name);
    setRelocatePath(currentPath || '');
    setRelocateError(null);
  };
  const submitRelocate = (name) => {
    if (!relocatePath.trim()) {
      setRelocateError(t('projects.relocatePathRequired'));
      return;
    }
    onRelocate?.(name, relocatePath.trim());
    setRelocating(null);
  };
  return { relocating, relocatePath, relocateError, setRelocatePath, submitRelocate, setRelocating, startRelocate };
}
