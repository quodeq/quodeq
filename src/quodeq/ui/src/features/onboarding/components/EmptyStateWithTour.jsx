import { TermHeader } from '../../../components/terminal/index.js';

const SKIPPED_STEPS_KEY = 'quodeq_onboarding_skipped';

function clearSkip() {
  try { localStorage.removeItem(SKIPPED_STEPS_KEY); } catch { /* ignore */ }
}

export default function EmptyStateWithTour({ onAdd, onTour, onBrowseRemote = null, isEvaluating = false }) {
  const blockedTitle = isEvaluating ? 'Cannot add a project while an evaluation is running' : undefined;
  return (
    <section className="empty-state empty-state--with-tour">
      <TermHeader name="projects" sub="no projects yet" />
      <p>
        {onBrowseRemote
          ? 'no local projects yet. your team’s online repository has published projects you can browse, or set up your own.'
          : 'set up your first repository. quodeq scans it locally and runs an evaluation against the standards you pick.'}
      </p>
      <div className="empty-state__actions">
        {onBrowseRemote && (
          <button
            type="button"
            className="term-btn--primary"
            onClick={onBrowseRemote}
          >
            browse remote repositories
          </button>
        )}
        <button
          type="button"
          className={`${onBrowseRemote ? 'term-btn--secondary' : 'term-btn--primary'}${isEvaluating ? ' is-disabled' : ''}`}
          onClick={() => { clearSkip(); onAdd(); }}
          aria-disabled={isEvaluating || undefined}
          title={blockedTitle}
        >
          add a project
        </button>
        <button
          type="button"
          className={`term-btn--secondary${isEvaluating ? ' is-disabled' : ''}`}
          onClick={() => { clearSkip(); onTour(); }}
          aria-disabled={isEvaluating || undefined}
          title={blockedTitle}
        >
          take the tour
        </button>
      </div>
    </section>
  );
}
