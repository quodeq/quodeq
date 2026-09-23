import { useEffect } from 'react';
import { listStandards, getProjectScan } from '../../../api/index.js';
import { saveDraft } from './useWizardDraft.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';

/**
 * The wizard's three boot/persist effects: fetch the standards list once,
 * save a draft on every step transition, and fetch the scan for a preset
 * project when the wizard is resumed into one.
 * @param {object} args
 * @param {object} args.wizard - useWizardState's bundle; its `state` drives
 *   the draft save and its intents receive the fetched scan.
 * @param {object} args.entry - how the wizard was opened (start step,
 *   presetProjectId, isFirstProject).
 * @param {(standards: Array) => void} args.setStandards - receives the
 *   standards filtered to the user's visible set, or [] if the fetch fails.
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
      .catch((err) => {
        console.warn('[useOnboardingEffects] resume-scan fetch failed:', err); // tolerate: onboarding still proceeds without the summary
      });
  }, [entry.presetProjectId]); // eslint-disable-line react-hooks/exhaustive-deps -- runs once per preset project; wizard is a new object every render and would refire the fetch
}
