import { useState } from 'react';
import { RepoInput } from '../../../evaluation/components/EvaluationForm.jsx';
import ScanProgress from '../../../evaluation/components/ScanProgress.jsx';
import FolderBrowser from '../../../evaluation/components/FolderBrowser.jsx';

export default function RepoScanStep({ state, actions, createProject, onContinue, onCancel }) {
  const sub = state.repoScanSubState;
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);

  async function handleSubmit() {
    if (!state.repo.value) return;
    actions.startScan();
    try {
      const { projectId, scanData } = await createProject({ repo: state.repo.value });
      actions.succeedScan(projectId, scanData);
    } catch (err) {
      actions.failScan({ message: err.message, status: err.status, existingProjectId: err.existingProjectId });
    }
  }

  function handleFolderSelect(path) {
    actions.setRepo({ value: path, source: 'local' });
    setFolderBrowserOpen(false);
  }

  return (
    <div className="onboarding-step onboarding-step--repo-scan">
      <h2>Add a repository</h2>
      <p className="onboarding-step__pitch">
        Paste a Git URL or pick a local folder. quodeq will scan it locally — no AI tokens used yet.
      </p>

      <div className={sub === 'idle' ? '' : 'onboarding-form-locked'}>
        <RepoInput
          repo={state.repo.value}
          onRepoChange={(value) => actions.setRepo({ value, source: 'url' })}
          onClear={() => actions.setRepo({ value: '' })}
          onBrowse={() => setFolderBrowserOpen(true)}
        />
        {sub === 'scanned' && (
          <button type="button" className="link-btn" onClick={actions.resetScan}>Edit repository</button>
        )}
      </div>

      {sub === 'scanning' && (
        <div className="onboarding-scan-progress">
          <ScanProgress />
          <p className="onboarding-scan-progress__hint">Cloning · Walking files · Detecting languages…</p>
        </div>
      )}

      {sub === 'error' && (
        <div className="onboarding-scan-error" role="alert">
          <p>{state.scanError?.message || 'Scan failed.'}</p>
          <div className="onboarding-step__actions">
            <button type="button" className="btn-primary" onClick={handleSubmit}>Try again</button>
            <button type="button" className="btn-secondary" onClick={actions.resetScan}>Edit repository</button>
          </div>
        </div>
      )}

      {sub === 'scanned' && (
        <div className="onboarding-scan-summary">
          <h3>We found:</h3>
          <p><strong>{state.scan?.total_files ?? 0} files</strong> in {Object.keys(state.scan?.languages || {}).length} languages</p>
          {Object.keys(state.scan?.languages || {}).length > 0 && (
            <ul className="onboarding-scan-summary__langs">
              {Object.entries(state.scan.languages).slice(0, 5).map(([lang, count]) => (
                <li key={lang}>{lang}: {count}</li>
              ))}
            </ul>
          )}
          <p>{state.scan?.branches?.length || 0} branches detected</p>
        </div>
      )}

      <div className="onboarding-step__actions">
        {sub === 'idle' && (
          <button type="button" className="btn-primary" onClick={handleSubmit} disabled={!state.repo.value}>Scan repository</button>
        )}
        {sub === 'scanned' && (
          <>
            <button type="button" className="btn-primary" onClick={onContinue}>Continue</button>
            <button type="button" className="btn-secondary" onClick={onCancel}>Save and finish setup later</button>
          </>
        )}
      </div>

      {folderBrowserOpen && (
        <FolderBrowser
          onSelect={handleFolderSelect}
          onClose={() => setFolderBrowserOpen(false)}
          title="Select Folder or File"
          confirmText="Use this path"
          showFiles
        />
      )}
    </div>
  );
}
