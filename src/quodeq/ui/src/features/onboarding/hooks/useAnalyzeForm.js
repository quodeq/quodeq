import { REPO_SOURCE } from '../onboardingVocab.js';
import { useFolderPicker } from '../../dashboard/hooks/useFolderPicker.jsx';
import { useWorkingCopy } from './useWorkingCopy.js';
import { t } from '../../../strings/index.js';

// A scheme (https://, ssh://, file://), an scp-style git@host:path, or a
// user@host:path reads as a url; anything else is a path on this machine.
const URL_SHAPE = /^(?:[a-z][a-z0-9+.-]*:\/\/|git@|[\w.-]+@[\w.-]+:)/i;

/**
 * Which source a typed value is: a git url or a local folder.
 * @param {string} value
 * @returns {string} REPO_SOURCE.URL or REPO_SOURCE.FOLDER
 */
export function inferRepoSource(value) {
  return URL_SHAPE.test((value || '').trim()) ? REPO_SOURCE.URL : REPO_SOURCE.FOLDER;
}

/**
 * The add panel's form: one field that takes a git url or a local folder
 * path (the source is read from the value), a `local folder` button that
 * fills it from the folder picker, and the working copy a url is cloned to.
 *
 * `request()` is what the add sends: the repository, its source and, only
 * when the user picked a root, `cloneDest`.
 *
 * @param {{ wizard: object }} args
 */
export function useAnalyzeForm({ wizard }) {
  const { value: repo } = wizard.state.repo;
  const { browseFolder, picker: repoPicker } = useFolderPicker({ title: t('onboarding.repoFolderPickerTitle') });
  const trimmed = repo.trim();
  const source = inferRepoSource(trimmed);
  const workingCopy = useWorkingCopy(source === REPO_SOURCE.URL ? trimmed : '');

  const request = () => ({
    repo: trimmed,
    source,
    ...(source === REPO_SOURCE.URL && workingCopy.cloneDest ? { cloneDest: workingCopy.cloneDest } : {}),
  });

  return {
    source,
    repo,
    setRepo: (value) => wizard.setRepo({ source: inferRepoSource(value), value }),
    browseRepoFolder: async () => {
      const path = await browseFolder();
      if (path) wizard.setRepo({ source: REPO_SOURCE.FOLDER, value: path });
    },
    workingCopy,
    canSubmit: Boolean(trimmed),
    request,
    // The folder browsers' modals (null while closed): render both.
    pickers: { repo: repoPicker, workingCopy: workingCopy.picker },
  };
}
