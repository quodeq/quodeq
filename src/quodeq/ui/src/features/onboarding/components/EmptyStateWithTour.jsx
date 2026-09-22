import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { removeKey } from '../../../adapters/storage.js';
import { SKIPPED_KEY } from '../wizardSteps.js';
import { evalBlockedClass, evalBlockedProps } from '../../../utils/evalBlocked.js';

function clearSkip() {
  removeKey(SKIPPED_KEY);
}

export default function EmptyStateWithTour({ onAdd, onTour, onBrowseRemote = null, isEvaluating = false }) {
  const blocked = evalBlockedProps(isEvaluating, t('onboarding.cannotAddWhileRunning'));
  // Both CTAs stay clickable while evaluating (aria-disabled, not disabled),
  // so each handler has to swallow the click itself before clearing the skip.
  const runAfterClearingSkip = (cb) => () => {
    if (isEvaluating) return;
    clearSkip();
    cb();
  };
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
          className={`${onBrowseRemote ? 'term-btn--secondary' : 'term-btn--primary'}${evalBlockedClass(isEvaluating)}`}
          onClick={runAfterClearingSkip(onAdd)}
          {...blocked}
        >
          {t('onboarding.addProject')}
        </button>
        <button
          type="button"
          className={`term-btn--secondary${evalBlockedClass(isEvaluating)}`}
          onClick={runAfterClearingSkip(onTour)}
          {...blocked}
        >
          {t('onboarding.takeTour')}
        </button>
      </div>
    </section>
  );
}
