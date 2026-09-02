import { useEffect } from 'react';
import { listStandards, getProjectScan } from '../../../api/index.js';
import { saveDraft } from './useWizardDraft.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';

/**
 * OnboardingWizard.jsx's three boot/persist effects: the standards fetch,
 * the per-step draft save, and the preset-project resume scan fetch.
 * Extracted verbatim.
 */
export function useOnboardingEffects({ wizard, entry, setStandards }) {
  // Fetch standards once when the step that needs them is reachable.
  // Filter to the user's visible-standards setting so the picker matches
  // what's enabled in the Standards tab. Lowercase both sides because the
  // default list and the storage payload use lowercase ids.
  useEffect(() => {
    const visibleSet = new Set(readVisibleStandardIds().map((id) => (id || '').toLowerCase()));
    listStandards()
      .then((all) => setStandards(all.filter((s) => visibleSet.has((s.id || '').toLowerCase()))))
      .catch(() => setStandards([]));
  }, []);

  // Persist a draft on every step transition or relevant state change.
  useEffect(() => {
    saveDraft({
      step: wizard.state.step,
      repo: wizard.state.repo,
      providerSelection: wizard.state.provider,
      providerView: wizard.state.providerView,
      standardIds: Array.from(wizard.state.standardIds),
      totalTimeLimitS: wizard.state.totalTimeLimitS,
    });
  }, [wizard.state.step, wizard.state.repo, wizard.state.provider, wizard.state.providerView, wizard.state.standardIds, wizard.state.totalTimeLimitS]);

  useEffect(() => {
    if (!entry.presetProjectId) return;
    // Fetch the project's scan data so the resume flow shows the same summary.
    getProjectScan(entry.presetProjectId)
      .then((scan) => {
        if (!scan) return;
        wizard.succeedScan(entry.presetProjectId, scan);
      })
      .catch(() => { /* tolerate scan fetch failure */ });
  }, [entry.presetProjectId]); // eslint-disable-line react-hooks/exhaustive-deps
}
