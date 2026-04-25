import { useState, useEffect } from 'react';
import EvaluationForm from './EvaluationForm.jsx';
import EvaluationStatus from './EvaluationStatus.jsx';
import ReEvaluateCard from './ReEvaluateCard.jsx';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';
import { TermHeader, SectionLabel } from '../../../components/terminal/index.js';

const TOAST_DISMISS_TIMEOUT_MS = 5000;

function EvaluateHelpSection() {
  return (
    <div className="panel evaluate-help-panel">
      <SectionLabel>how_it_works</SectionLabel>
      <div className="help-steps">
        <div className="help-step">
          <div className="step-number">1</div>
          <div className="step-content">
            <h4>Provide Repository</h4>
            <p>Enter a GitHub URL, SSH path, or local filesystem path to the repository you want to evaluate.</p>
          </div>
        </div>
        <div className="help-step">
          <div className="step-number">2</div>
          <div className="step-content">
            <h4>Select Dimensions</h4>
            <p>Choose which quality dimensions to analyze. Each dimension covers different aspects of code quality.</p>
          </div>
        </div>
        <div className="help-step">
          <div className="step-number">3</div>
          <div className="step-content">
            <h4>Review Results</h4>
            <p>Once complete, view detailed findings, grades, and actionable recommendations in the Overview.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

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

function EvaluateHeader() {
  // Page title stays steady ("evaluate"); the live "in progress / failed /
  // done" state is carried by the JobHeader card title below to avoid
  // doubling the same status on screen.
  return (
    <header className="evaluate-header evaluate-header--terminal">
      <div className="evaluate-header__left">
        <TermHeader
          name="evaluate"
          sub="run a comprehensive code quality evaluation on any repository"
        />
      </div>
      <ActiveProviderBadge />
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

export default function EvaluateScreen({ evaluation, context, actions }) {
  const { job, jobError, liveViolations } = evaluation;
  const { selectedProject, projectInfo } = context;
  const { onStart: onStartEvaluation, onDismiss, onCancel } = actions;
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
      <EvaluateHeader />

      <div className="evaluate-content">
        {!job && selectedProject && (
          <ReEvaluateCard project={selectedProject} projectInfo={projectInfo} onStart={wrappedOnStart} disabled={false} />
        )}

        {!job && (
          <div className="panel evaluate-panel">
            <SectionLabel>{selectedProject ? 'evaluate_new_repository' : 'evaluate_repository'}</SectionLabel>
            <EvaluationForm onStart={wrappedOnStart} disabled={false} selectedProject={projectInfo} />
          </div>
        )}

        <EvaluationStatus job={job} liveViolations={liveViolations} onDismiss={onDismiss} onCancel={onCancel} hasEvaluations={!!selectedProject} />

        {!job && <EvaluateHelpSection />}
      </div>

      {jobError && toastVisible && (
        <ErrorToast key={toastKey} message={jobError} onDismiss={() => setToastVisible(false)} />
      )}
    </section>
  );
}
