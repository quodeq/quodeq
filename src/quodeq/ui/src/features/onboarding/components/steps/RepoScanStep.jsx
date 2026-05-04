import { useState } from 'react';
import { RepoInput } from '../../../evaluation/components/EvaluationForm.jsx';
import ScanProgress from '../../../evaluation/components/ScanProgress.jsx';
import FolderBrowser from '../../../evaluation/components/FolderBrowser.jsx';

export default function RepoScanStep({ state, actions, createProject, getProjectInfo, onContinue, onCancel }) {
  const sub = state.repoScanSubState;
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);

  // 409 + existingProjectId means a project was already registered for this
  // repo. If it has no evaluations yet, silently resume into it — the user
  // most likely abandoned an earlier onboarding attempt. If it does have
  // evaluations, fall through to the normal error UI so the user can decide.
  async function tryResumeExisting(existingProjectId) {
    try {
      const info = await getProjectInfo(existingProjectId);
      if (info.runsCount > 0) return false;
      const scanRes = await fetch(`/api/projects/${encodeURIComponent(existingProjectId)}/scan`);
      if (!scanRes.ok) return false;
      const scanData = await scanRes.json();
      actions.succeedScan(existingProjectId, scanData);
      return true;
    } catch {
      return false;
    }
  }

  async function handleSubmit() {
    if (!state.repo.value) return;
    actions.startScan();
    try {
      const { projectId, scanData } = await createProject({ repo: state.repo.value });
      actions.succeedScan(projectId, scanData);
    } catch (err) {
      if (err.status === 409 && err.existingProjectId) {
        const resumed = await tryResumeExisting(err.existingProjectId);
        if (resumed) return;
      }
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

      {sub === 'scanned' && (() => {
        const totalFiles = state.scan?.total_files ?? 0;
        const langs = state.scan?.languages || {};
        const langCount = Object.keys(langs).length;
        const branchCount = state.scan?.branches?.length ?? 0;
        const topLangs = Object.entries(langs).sort((a, b) => b[1] - a[1]).slice(0, 8);
        return (
          <div className="onboarding-scan-summary">
            <div className="onboarding-scan-summary__stats">
              <div className="onboarding-scan-summary__stat">
                <span className="onboarding-scan-summary__stat-value">{totalFiles}</span>
                <span className="onboarding-scan-summary__stat-label">{totalFiles === 1 ? 'file' : 'files'}</span>
              </div>
              <div className="onboarding-scan-summary__stat">
                <span className="onboarding-scan-summary__stat-value">{langCount}</span>
                <span className="onboarding-scan-summary__stat-label">{langCount === 1 ? 'language' : 'languages'}</span>
              </div>
              <div className="onboarding-scan-summary__stat">
                <span className="onboarding-scan-summary__stat-value">{branchCount}</span>
                <span className="onboarding-scan-summary__stat-label">{branchCount === 1 ? 'branch' : 'branches'}</span>
              </div>
            </div>
            {topLangs.length > 0 && (
              <div className="onboarding-scan-summary__langs">
                {topLangs.map(([lang, count]) => (
                  <span key={lang} className="onboarding-scan-summary__lang-pill">
                    <span className="onboarding-scan-summary__lang-name">{lang}</span>
                    <span className="onboarding-scan-summary__lang-count">{count}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })()}

      <div className="onboarding-step__actions">
        {sub === 'idle' && (
          <button type="button" className="btn-primary" onClick={handleSubmit} disabled={!state.repo.value}>Scan repository</button>
        )}
        {sub === 'scanned' && (
          <button type="button" className="btn-primary" onClick={onContinue}>Continue</button>
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
