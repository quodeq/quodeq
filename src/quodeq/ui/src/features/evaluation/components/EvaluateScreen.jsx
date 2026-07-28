import { useState, useEffect } from 'react';
import EvaluationStatus from './EvaluationStatus.jsx';
import ReEvaluateCard from './ReEvaluateCard.jsx';
import { ACTIVE_PROVIDER_KEY } from '../../../constants.js';
import { resolveProviderSettings } from '../../../utils/effectiveProviderSettings.js';
import { TermHeader } from '../../../components/terminal/index.js';

const TOAST_DISMISS_TIMEOUT_MS = 5000;

export function readBudgetSeconds(storage = localStorage) {
  const provider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  if (!provider) return 0;
  // Same resolution the start payload and the Settings screen use, so the
  // header can never claim a limit the run won't get.
  return resolveProviderSettings(provider, storage).timeLimitS;
}

function EvaluateHeader() {
  // Page title stays steady ("evaluate"); the live "in progress / failed /
  // done" state is carried by the JobHeader card title below to avoid
  // doubling the same status on screen. Budget lives in the progress footer
  // while a run is on; the model lives in the cards' identity strips.
  return (
    <header className="evaluate-header evaluate-header--terminal">
      <div className="evaluate-header__left">
        <TermHeader
          name="evaluate"
          sub="run a comprehensive code quality evaluation on any repository"
        />
      </div>
    </header>
  );
}

function sanitizeErrorMessage(message) {
  if (typeof message !== 'string') return 'An error occurred';
  if (message.includes('\n') || /[/\\](?:usr|home|tmp|var|etc|src|node_modules)/.test(message) || message.length > 120) {
    console.error('Raw error:', message);
    return 'An error occurred. Check the console for details.';
  }
  return message;
}

function ErrorToast({ message, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, TOAST_DISMISS_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  return (
    <button type="button" className="job-error-toast" onClick={onDismiss}>
      {sanitizeErrorMessage(message)}
    </button>
  );
}

function NoProjectSelected({ onGoToProjects }) {
  return (
    <div className="panel evaluate-panel evaluate-panel--terminal evaluate-no-project">
      <div className="evaluate-panel__top">
        <TermHeader name="no_project" sub="pick or add a project to start" />
      </div>
      <p className="evaluate-no-project__hint">
        Add or pick a project from Projects to run an evaluation.
      </p>
      {onGoToProjects && (
        <button
          type="button"
          className="term-btn term-btn--primary"
          onClick={onGoToProjects}
        >
          <span aria-hidden="true">▸</span> go to projects
        </button>
      )}
    </div>
  );
}

export default function EvaluateScreen({ evaluation, context, actions }) {
  const { job, jobError, liveViolations } = evaluation;
  const { selectedProject, projectInfo, jobProjectInfo, startedProjectInfo, preselectDims } = context;
  const { onStart: onStartEvaluation, onDismiss, onCancel, onGoToProjects, onGoToSettings } = actions;
  const [toastKey, setToastKey] = useState(0);
  const [toastVisible, setToastVisible] = useState(false);

  useEffect(() => {
    if (jobError) setToastVisible(true);
  }, [jobError, toastKey]);

  const wrappedOnStart = (payload) => {
    setToastVisible(false);
    setToastKey(k => k + 1);
    // Pass the result through: false means the start was blocked, and the
    // card uses that to keep one-shot state (clean-scan "once") armed.
    return onStartEvaluation(payload);
  };

  return (
    <section className="evaluate-screen">
      <EvaluateHeader />

      <div className="evaluate-content">
        {!job && selectedProject && (
          <ReEvaluateCard project={selectedProject} projectInfo={projectInfo} onStart={wrappedOnStart} disabled={false} preselectDims={preselectDims} onGoToSettings={onGoToSettings} onGoToProjects={onGoToProjects} />
        )}

        {!job && !selectedProject && (
          <NoProjectSelected onGoToProjects={onGoToProjects} />
        )}

        <EvaluationStatus
          job={job}
          jobProjectInfo={jobProjectInfo}
          startedProjectInfo={startedProjectInfo}
          liveViolations={liveViolations}
          onDismiss={onDismiss}
          onCancel={onCancel}
          hasEvaluations={!!selectedProject}
        />
      </div>

      {jobError && toastVisible && (
        <ErrorToast key={toastKey} message={jobError} onDismiss={() => setToastVisible(false)} />
      )}
    </section>
  );
}
