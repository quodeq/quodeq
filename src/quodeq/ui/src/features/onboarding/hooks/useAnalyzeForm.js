import { useEffect, useState } from 'react';
import { REPO_SOURCE } from '../onboardingVocab.js';
import { defaultStandardIds, describeStandards, toggledStandards } from '../standardSelection.js';
import { useFolderPicker } from '../../dashboard/hooks/useFolderPicker.jsx';
import { useReviewer } from './useReviewer.js';
import { useWorkingCopy } from './useWorkingCopy.js';
import { t } from '../../../strings/index.js';

// The standard row: the wizard's pick (the default until the user changes
// it), how it reads, and the picker's open state.
function useStandardPick({ wizard, standards }) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const picked = Array.from(wizard.state.standardIds);
  const ids = picked.length > 0 ? picked : defaultStandardIds(standards);
  return {
    ids,
    ...describeStandards(standards, ids),
    // False while the standards list is still loading (no name to show yet).
    ready: standards.length > 0,
    pickerOpen,
    openPicker: () => setPickerOpen(true),
    closePicker: () => setPickerOpen(false),
    pick: (id) => wizard.pickStandards(toggledStandards(standards, ids, id)),
  };
}

// The reviewer feeds the wizard's provider (and the configured time limit),
// which the launch payload reads. Keyed on the values alone: the wizard
// bundle is a new object every render, its setters are stable.
function useSyncProvider(wizard, provider) {
  const { id, model, classification } = provider.selection ?? {};
  const { setProvider, setTimeLimit } = wizard;
  useEffect(() => {
    if (id) setProvider({ id, model: model ?? null, classification: classification ?? null });
  }, [id, model, classification, setProvider]);
  useEffect(() => {
    if (provider.timeLimitS !== null) setTimeLimit(provider.timeLimitS);
  }, [provider.timeLimitS, setTimeLimit]);
}

/**
 * The analyze screen's form: the repository (a pasted url or a picked folder,
 * kept in the wizard's `repo`), its working copy, who reviews it and against
 * which standard. A returning user (a provider configured in Settings) sees
 * the last two `collapsed` into one summary line until `expand`.
 *
 * `request()` is what the launch sends: the repository, its source, the
 * standard ids and, only when the user picked a root, `cloneDest`.
 *
 * @param {{ wizard: object, standards: object[], detect?: () => Promise<object[]> }} args
 */
export function useAnalyzeForm({ wizard, standards, detect }) {
  const { source, value: repo } = wizard.state.repo;
  const [expanded, setExpanded] = useState(false);
  const { browseFolder, picker: repoPicker } = useFolderPicker({ title: t('onboarding.repoFolderPickerTitle') });
  const workingCopy = useWorkingCopy(source === REPO_SOURCE.URL ? repo : '');
  const provider = useReviewer({ detect });
  const standard = useStandardPick({ wizard, standards });
  useSyncProvider(wizard, provider);

  const trimmed = repo.trim();
  // A model is required for every provider: a detection without one is not ready.
  const reviewerReady = provider.configured || Boolean(provider.selection?.model);
  const request = () => ({
    repo: trimmed,
    source,
    standardIds: standard.ids,
    ...(source === REPO_SOURCE.URL && workingCopy.cloneDest ? { cloneDest: workingCopy.cloneDest } : {}),
  });

  return {
    source,
    setSource: (next) => { if (next !== source) wizard.setRepo({ source: next, value: '' }); },
    repo,
    setRepo: (value) => wizard.setRepo({ value }),
    browseRepoFolder: async () => {
      const path = await browseFolder();
      if (path) wizard.setRepo({ value: path });
    },
    workingCopy,
    provider,
    standard,
    collapsed: provider.configured && !expanded,
    expand: () => setExpanded(true),
    canSubmit: Boolean(trimmed) && standard.ids.length > 0 && reviewerReady,
    request,
    // The folder browsers' modals (null while closed): render both.
    pickers: { repo: repoPicker, workingCopy: workingCopy.picker },
  };
}
