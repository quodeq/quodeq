import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { removeKey } from '../../../adapters/storage.js';
import { SKIPPED_KEY } from '../hooks/useWizardDraft.js';

function clearSkip() {
  removeKey(SKIPPED_KEY);
}

export default function EmptyStateWithTour({ onAdd, onTour, onBrowseRemote = null, isEvaluating = false }) {
  const blockedTitle = isEvaluating ? t('onboarding.cannotAddWhileRunning') : undefined;
  return (
    <section className="empty-state empty-state--with-tour">
      <TermHeader name="projects" sub={t('map.subNoProjects')} />
      <p>
        {onBrowseRemote
          ? t('onboarding.noLocalProjectsShared')
          : t('onboarding.noProjectsFirstRepo')}
      </p>
      <div className="empty-state__actions">
        {onBrowseRemote && (
          <button
            type="button"
            className="term-btn--primary"
            onClick={onBrowseRemote}
          >
            {t('onboarding.browseRemote')}
          </button>
        )}
        <button
          type="button"
          className={`${onBrowseRemote ? 'term-btn--secondary' : 'term-btn--primary'}${isEvaluating ? ' is-disabled' : ''}`}
          onClick={() => { if (isEvaluating) return; clearSkip(); onAdd(); }}
          aria-disabled={isEvaluating || undefined}
          title={blockedTitle}
        >
          {t('onboarding.addProject')}
        </button>
        <button
          type="button"
          className={`term-btn--secondary${isEvaluating ? ' is-disabled' : ''}`}
          onClick={() => { if (isEvaluating) return; clearSkip(); onTour(); }}
          aria-disabled={isEvaluating || undefined}
          title={blockedTitle}
        >
          {t('onboarding.takeTour')}
        </button>
      </div>
    </section>
  );
}
