import { useState } from 'react';
import CloneTargetStep from '../../onboarding/components/steps/CloneTargetStep.jsx';
import { registerProject } from '../../../api/index.js';
import { t } from '../../../strings/index.js';
import { writeString } from '../../../adapters/storage.js';

/**
 * Surfaces a "Complete setup" CTA on the project view for legacy projects
 * registered with `location: "online"` (no local clone). Click reveals the
 * onboarding `CloneTargetStep`; submit re-registers the project with a
 * `cloneDest` (or `ephemeral: true`), which overwrites repository_info.json
 * and turns the project into a normal local project.
 */
export default function IncompleteSetupCard({ projectInfo, onComplete }) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!projectInfo || projectInfo.location !== 'online') return null;
  const repoUrl = projectInfo.path || projectInfo.repo || '';

  async function handleSubmit({ cloneDest, ephemeral }) {
    setSubmitting(true);
    setError(null);
    try {
      const result = await registerProject({ repo: repoUrl, cloneDest, ephemeral });
      if (cloneDest) {
        writeString('quodeq.lastCloneRoot', cloneDest);
      }
      onComplete?.(result);
    } catch (err) {
      setError(err?.message || t('overview.cloneFailed'));
    } finally {
      setSubmitting(false);
    }
  }

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
