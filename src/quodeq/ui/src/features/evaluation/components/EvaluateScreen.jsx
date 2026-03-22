import EvaluationForm from './EvaluationForm.jsx';
import EvaluationStatus from './EvaluationStatus.jsx';
import ReEvaluateCard from './ReEvaluateCard.jsx';
import PowerSelector from './PowerSelector.jsx';

export default function EvaluateScreen({ evaluation, context, actions }) {
  const { job, jobError, liveViolations } = evaluation;
  const { selectedProject, analysisPower, onAnalysisPowerChange } = context;
  const { onStart: onStartEvaluation, onDismiss, onCancel } = actions;

  return (
    <section className="evaluate-screen">
      <header className="evaluate-header">
        <div className="evaluate-header-content">
          <div className={`evaluate-icon${job?.status === 'running' ? ' running' : ''}`}>
            {/* Static layer — visible when idle */}
            <div className="eval-icon-static">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="7" />
                <line x1="16.5" y1="16.5" x2="21" y2="21" />
                <line x1="8" y1="11" x2="14" y2="11" />
                <line x1="11" y1="8" x2="11" y2="14" />
              </svg>
            </div>
            {/* Animated layer — visible when running */}
            <div className="eval-icon-animated">
              <span className="eval-file-chip" style={{animationDelay: '0s'}} />
              <span className="eval-file-chip" style={{animationDelay: '0.55s'}} />
              <span className="eval-file-chip" style={{animationDelay: '1.1s'}} />
              <svg className="eval-glass-sweep" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="7" />
                <line x1="16.5" y1="16.5" x2="21" y2="21" />
                <line x1="8" y1="11" x2="14" y2="11" />
                <line x1="11" y1="8" x2="11" y2="14" />
              </svg>
            </div>
          </div>
          <div>
            <h1>Evaluate Repository</h1>
            <p className="evaluate-subtitle">Run a comprehensive code quality evaluation on any repository</p>
          </div>
        </div>
        <PowerSelector value={analysisPower} onChange={onAnalysisPowerChange} />
      </header>

      <div className="evaluate-content">
        {!job && selectedProject && (
          <ReEvaluateCard
            project={selectedProject}
            onStart={onStartEvaluation}
            disabled={false}
          />
        )}

        {!job && (
          <div className="panel evaluate-panel">
            <div className="panel-header">
              <h3>{selectedProject ? 'Evaluate a new repository' : 'Evaluate a Repository'}</h3>
            </div>
            <EvaluationForm onStart={onStartEvaluation} disabled={false} />
          </div>
        )}

        {jobError && <div className="job-error-banner">Evaluation failed. Please check your inputs and try again.</div>}
        <EvaluationStatus job={job} liveViolations={liveViolations} onDismiss={onDismiss} onCancel={onCancel} />

        {!job && <div className="panel evaluate-help-panel">
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
        </div>}
      </div>
    </section>
  );
}
