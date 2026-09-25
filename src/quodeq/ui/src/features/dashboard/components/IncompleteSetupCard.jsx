import CloneTargetStep from '../../onboarding/components/steps/CloneTargetStep.jsx';
import { useCompleteSetup } from '../hooks/useCompleteSetup.js';
import { t } from '../../../strings/index.js';
import { PROJECT_LOCATION } from '../../../models/project.js';

/**
 * Surfaces a "Complete setup" CTA on the project view for legacy projects
 * registered with `location: "online"` (no local clone). Click reveals the
 * onboarding `CloneTargetStep`; submit re-registers the project with a
 * `cloneDest` (or `ephemeral: true`), which overwrites repository_info.json
 * and turns the project into a normal local project.
 */
export default function IncompleteSetupCard({ projectInfo, onComplete }) {
  const repoUrl = projectInfo?.path || projectInfo?.repo || '';
  // useCompleteSetup runs unconditionally, before the early return below, so
  // hook order stays stable across the legacy-online / not-applicable branches.
  const { open, setOpen, submitting, error, handleSubmit } = useCompleteSetup({ repoUrl, onComplete });

  if (!projectInfo || projectInfo.location !== PROJECT_LOCATION.ONLINE) return null;

  if (!open) {
    return (
      <div className="incomplete-setup-card">
        <p>{t('overview.incompleteSetupBody')}</p>
        <button type="button" className="term-btn term-btn--primary" onClick={() => setOpen(true)}>
          {t('overview.completeSetup')}
        </button>
      </div>
    );
  }

  return (
    <CloneTargetStep
      repoUrl={repoUrl}
      onSubmit={handleSubmit}
      onBack={() => setOpen(false)}
      submitting={submitting}
      error={error}
    />
  );
}
