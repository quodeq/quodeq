import { useEffect, useMemo, useState } from 'react';
import { registerProject, listStandards } from '../../../api/index.js';
import { useWizardState } from '../hooks/useWizardState.js';
import { saveDraft, clearDraft } from '../hooks/useWizardDraft.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import StepProgress from './StepProgress.jsx';
import WelcomeStep from './steps/WelcomeStep.jsx';
import RepoScanStep from './steps/RepoScanStep.jsx';
import ProviderStep from './steps/ProviderStep.jsx';
import StandardLaunchStep from './steps/StandardLaunchStep.jsx';
import '../../../styles/onboarding.css';

const STEP_ORDER = ['welcome', 'repo-scan', 'provider', 'standard-launch'];
const SKIPPED_STEPS_KEY = 'quodeq_onboarding_skipped';

function visibleSteps(_currentStep, _isFirstProject, providerConfigured) {
  // Welcome is excluded from numeric counter.
  const seen = ['repo-scan'];
  if (!providerConfigured) seen.push('provider');
  seen.push('standard-launch');
  return seen;
}

export default function OnboardingWizard({ entry, onClose, onLaunch }) {
  const initialStep = entry.startStep || 'welcome';
  const wizard = useWizardState({ initial: { step: initialStep, isFirstProject: entry.isFirstProject ?? true } });
  const [standards, setStandards] = useState([]);

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
    fetch(`/api/projects/${encodeURIComponent(entry.presetProjectId)}/scan`)
      .then((res) => res.ok ? res.json() : null)
      .then((scan) => {
        if (!scan) return;
        wizard.succeedScan(entry.presetProjectId, scan);
      })
      .catch(() => { /* tolerate scan fetch failure */ });
  }, [entry.presetProjectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const providerConfigured = Boolean(wizard.state.provider.id && wizard.state.provider.model);
  const visible = useMemo(
    () => visibleSteps(wizard.state.step, wizard.state.isFirstProject, providerConfigured),
    [wizard.state.step, wizard.state.isFirstProject, providerConfigured],
  );
  const currentIndex = visible.indexOf(wizard.state.step) + 1;

  function handleSkipWelcome() {
    try { localStorage.setItem(SKIPPED_STEPS_KEY, 'true'); } catch { /* ignore */ }
    clearDraft();
    onClose({ saved: false });
  }

  function handleSavedExit() {
    clearDraft();
    onClose({ saved: true, projectId: wizard.state.projectId });
  }

  function handleClose() {
    if (wizard.state.repoScanSubState === 'scanned') {
      handleSavedExit();
    } else {
      clearDraft();
      onClose({ saved: false });
    }
  }

  function handleLaunch(standardIds) {
    wizard.startLaunch();
    clearDraft();
    onLaunch({
      projectId: wizard.state.projectId,
      repo: wizard.state.repo.value,
      scopePath: wizard.state.repo.scopePath || null,
      branch: wizard.state.repo.branch || null,
      provider: wizard.state.provider,
      standardIds,
      totalTimeLimitS: wizard.state.totalTimeLimitS,
    });
  }

  function nextStep() {
    const i = STEP_ORDER.indexOf(wizard.state.step);
    let next = STEP_ORDER[i + 1] || wizard.state.step;
    // Auto-skip Provider if already configured.
    if (next === 'provider' && providerConfigured) next = 'standard-launch';
    wizard.goToStep(next);
  }

  function prevStep() {
    const i = STEP_ORDER.indexOf(wizard.state.step);
    if (i > 0) wizard.goToStep(STEP_ORDER[i - 1]);
  }

  return (
    <div className="onboarding-wizard" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
      <button type="button" className="onboarding-wizard__close" aria-label="Close onboarding" onClick={handleClose}>×</button>

      {wizard.state.step !== 'welcome' && (
        <StepProgress current={currentIndex} total={visible.length} />
      )}

      {wizard.state.step === 'welcome' && (
        <WelcomeStep onStart={() => wizard.goToStep('repo-scan')} onSkip={handleSkipWelcome} />
      )}

      {wizard.state.step === 'repo-scan' && (
        <RepoScanStep
          state={wizard.state}
          actions={wizard}
          createProject={registerProject}
          onContinue={nextStep}
          onCancel={handleSavedExit}
        />
      )}

      {wizard.state.step === 'provider' && (
        <ProviderStep
          state={wizard.state}
          actions={wizard}
          onContinue={nextStep}
          onBack={prevStep}
        />
      )}

      {wizard.state.step === 'standard-launch' && (
        <StandardLaunchStep
          state={wizard.state}
          actions={wizard}
          standards={standards}
          onLaunch={handleLaunch}
          onCancel={handleSavedExit}
          onBack={prevStep}
        />
      )}
    </div>
  );
}
