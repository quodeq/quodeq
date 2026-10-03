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
  if (!projectInfo || projectInfo.location !== PROJECT_LOCATION.ONLINE) return null;
  return <SetupFlow repoUrl={projectInfo.path || projectInfo.repo || ''} onComplete={onComplete} />;
}

// The flow itself, mounted only for a legacy online project: it follows the
// shared clone slot (a url completes as a 202 job), so its hooks live here
// rather than above the gate.
function SetupFlow({ repoUrl, onComplete }) {
  const { open, setOpen, submitting, error, handleSubmit } = useCompleteSetup({ repoUrl, onComplete });

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
