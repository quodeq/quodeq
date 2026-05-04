const SKIPPED_STEPS_KEY = 'quodeq_onboarding_skipped';

function clearSkip() {
  try { localStorage.removeItem(SKIPPED_STEPS_KEY); } catch { /* ignore */ }
}

export default function EmptyStateWithTour({ onAdd, onTour, isEvaluating = false }) {
  const blockedTitle = isEvaluating ? 'Cannot add a project while an evaluation is running' : undefined;
  return (
    <section className="empty-state empty-state--with-tour">
      <h2>No projects yet.</h2>
      <p>Set up your first repository — quodeq scans it locally and runs an evaluation against the standards you pick.</p>
      <div className="empty-state__actions">
        <button
          type="button"
          className="btn-primary"
          onClick={() => { clearSkip(); onAdd(); }}
          disabled={isEvaluating}
          title={blockedTitle}
        >
          Add a project
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => { clearSkip(); onTour(); }}
          disabled={isEvaluating}
          title={blockedTitle}
        >
          Take the tour
        </button>
      </div>
    </section>
  );
}
