import EvaluationForm from './EvaluationForm.jsx';
import EvaluationStatus from './EvaluationStatus.jsx';
import ReEvaluateCard from './ReEvaluateCard.jsx';

const INITIAL_ANIM_DELAY = '0s';
const CHIP_DELAY_1 = '0.55s';
const CHIP_DELAY_2 = '1.1s';

function EvaluateHelpSection() {
  return (
    <div className="panel evaluate-help-panel">
      <div className="panel-header">
        <h3>How It Works</h3>
      </div>
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

import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';

function ActiveProviderBadge() {
  const provider = localStorage.getItem(ACTIVE_PROVIDER_KEY) || '';
  const model = localStorage.getItem(providerKey(provider, 'model')) || '';
  if (!provider) return null;
  return (
    <div className="eval-provider-badge">
      <span className="eval-provider-name">{provider}</span>
      {model && <span className="eval-provider-model">{model}</span>}
    </div>
  );
}

function MagnifierIcon({ className }) {
  return (
    <svg className={className} width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <line x1="16.5" y1="16.5" x2="21" y2="21" />
      <line x1="8" y1="11" x2="14" y2="11" />
      <line x1="11" y1="8" x2="11" y2="14" />
    </svg>
  );
}

function EvaluateHeader({ isRunning }) {
  return (
    <header className="evaluate-header">
      <div className="evaluate-header-content">
        <div className={`evaluate-icon${isRunning ? ' running' : ''}`}>
          <div className="eval-icon-static">
            <MagnifierIcon />
          </div>
          <div className="eval-icon-animated">
            <span className="eval-file-chip" style={{animationDelay: INITIAL_ANIM_DELAY}} />
            <span className="eval-file-chip" style={{animationDelay: CHIP_DELAY_1}} />
            <span className="eval-file-chip" style={{animationDelay: CHIP_DELAY_2}} />
            <MagnifierIcon className="eval-glass-sweep" />
          </div>
        </div>
        <div>
          <h1>Evaluate Repository</h1>
          <p className="evaluate-subtitle">Run a comprehensive code quality evaluation on any repository</p>
        </div>
      </div>
      <ActiveProviderBadge />
    </header>
  );
}

import { useState, useEffect, useRef } from 'react';

function ErrorToast({ message, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 5000);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  return (
    <div className="job-error-toast" onClick={onDismiss}>
      {typeof message === 'string' ? message.slice(0, 200) : 'An error occurred'}
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
      <EvaluateHeader isRunning={job?.status === 'running'} />

      <div className="evaluate-content">
        {!job && selectedProject && (
          <ReEvaluateCard project={selectedProject} projectInfo={projectInfo} onStart={wrappedOnStart} disabled={false} />
        )}

        {!job && (
          <div className="panel evaluate-panel">
            <div className="panel-header">
              <h3>{selectedProject ? 'Evaluate a new repository' : 'Evaluate a Repository'}</h3>
            </div>
            <EvaluationForm onStart={wrappedOnStart} disabled={false} selectedProject={projectInfo} />
          </div>
        )}

        <EvaluationStatus job={job} liveViolations={liveViolations} onDismiss={onDismiss} onCancel={onCancel} />

        {!job && <EvaluateHelpSection />}
      </div>

      {jobError && toastVisible && (
        <ErrorToast key={toastKey} message={jobError} onDismiss={() => setToastVisible(false)} />
      )}
    </section>
  );
}
