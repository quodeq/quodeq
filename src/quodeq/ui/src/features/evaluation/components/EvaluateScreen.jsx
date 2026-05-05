import { useState, useEffect } from 'react';
import EvaluationStatus from './EvaluationStatus.jsx';
import ReEvaluateCard from './ReEvaluateCard.jsx';
import CountdownTimer from './CountdownTimer.jsx';
import { ACTIVE_PROVIDER_KEY, DEFAULT_TIME_LIMIT_S, providerKey } from '../../../constants.js';
import { TermHeader } from '../../../components/terminal/index.js';

const TOAST_DISMISS_TIMEOUT_MS = 5000;

function ActiveProviderBadge({ storage = localStorage }) {
  const provider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  const model = storage.getItem(providerKey(provider, 'model')) || '';
  if (!provider) return null;
  return (
    <div className="eval-provider-badge">
      <span className="eval-provider-name">{provider}</span>
      {model && <span className="eval-provider-model">{model}</span>}
    </div>
  );
}

function readBudgetSeconds(storage = localStorage) {
  const provider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  if (!provider) return 0;
  // Read new key first; fall back to legacy 'pool-budget' for back-compat.
  const raw = storage.getItem(providerKey(provider, 'time-limit'))
    ?? storage.getItem(providerKey(provider, 'pool-budget'));
  if (raw === null || raw === undefined) return provider === 'ollama' ? 0 : DEFAULT_TIME_LIMIT_S;
  const parsed = parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function EvaluateHeader({ job }) {
  // Page title stays steady ("evaluate"); the live "in progress / failed /
  // done" state is carried by the JobHeader card title below to avoid
  // doubling the same status on screen.
  const deadlineAt = job?.deadlineAt ?? null;
  const phase = job?.phase ?? job?.status ?? null;
  const budgetSeconds = readBudgetSeconds();
  return (
    <header className="evaluate-header evaluate-header--terminal">
      <div className="evaluate-header__left">
        <TermHeader
          name="evaluate"
          sub="run a comprehensive code quality evaluation on any repository"
        />
      </div>
      <div className="evaluate-header__right">
        <CountdownTimer deadlineAt={deadlineAt} budgetSeconds={budgetSeconds} phase={phase} />
        <ActiveProviderBadge />
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
    <div className="job-error-toast" onClick={onDismiss}>
      {sanitizeErrorMessage(message)}
    </div>
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
  const { selectedProject, projectInfo } = context;
  const { onStart: onStartEvaluation, onDismiss, onCancel, onGoToProjects } = actions;
  const [toastKey, setToastKey] = useState(0);
  const [toastVisible, setToastVisible] = useState(false);

  useEffect(() => {
    if (jobError) setToastVisible(true);
  }, [jobError, toastKey]);

  const wrappedOnStart = (payload) => {
    setToastVisible(false);
    setToastKey(k => k + 1);
    onStartEvaluation(payload);
  };

  return (
    <section className="evaluate-screen">
      <EvaluateHeader job={job} />

      <div className="evaluate-content">
        {!job && selectedProject && (
          <ReEvaluateCard project={selectedProject} projectInfo={projectInfo} onStart={wrappedOnStart} disabled={false} />
        )}

        {!job && !selectedProject && (
          <NoProjectSelected onGoToProjects={onGoToProjects} />
        )}

        <EvaluationStatus job={job} liveViolations={liveViolations} onDismiss={onDismiss} onCancel={onCancel} hasEvaluations={!!selectedProject} />
      </div>

      {jobError && toastVisible && (
        <ErrorToast key={toastKey} message={jobError} onDismiss={() => setToastVisible(false)} />
      )}
    </section>
  );
}
