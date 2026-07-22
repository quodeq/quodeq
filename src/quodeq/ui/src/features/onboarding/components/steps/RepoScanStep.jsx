import { useState } from 'react';
import { TermHeader, TermInput, StatStrip, Stat } from '../../../../components/terminal/index.js';
import ScanProgress from '../../../evaluation/components/ScanProgress.jsx';
import FolderBrowser from '../../../evaluation/components/FolderBrowser.jsx';
import CloneTargetStep from './CloneTargetStep.jsx';

const URL_RE = /^(https?:\/\/|git@|ssh:\/\/|git:\/\/)/i;
const CLONE_DEST_STORAGE_KEY = 'quodeq.lastCloneRoot';

// Map backend error codes (Task A8) to user-facing messages.
function friendlyCloneError(err) {
  const code = err?.code;
  switch (code) {
    case 'AUTH_REQUIRED':
      return "Couldn't clone. If this is a private repo, make sure `git clone <url>` works in your terminal first.";
    case 'NETWORK_ERROR':
      return "Couldn't reach the remote. Check your connection and try again.";
    case 'REPO_NOT_FOUND':
      return 'Repository not found. Check the URL and try again.';
    case 'DEST_EXISTS':
      return 'That folder already contains files. Pick a different location, or use the existing directory as a local-path project.';
    case 'DISK_ERROR':
      return err?.message || 'A disk error occurred. Check available space and permissions.';
    default:
      return err?.message || 'Clone failed.';
  }
}

export default function RepoScanStep({ state, actions, createProject, getProjectInfo, onContinue, onCancel, stepIndex = 0, stepTotal = 0 }) {
  const sub = state.repoScanSubState;
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);
  const [subStep, setSubStep] = useState('input'); // 'input' | 'cloneTarget'
  const [cloneSubmitting, setCloneSubmitting] = useState(false);
  const [cloneError, setCloneError] = useState(null);

  // 409 + existingProjectId means a project was already registered for this
  // repo. If it has no evaluations yet, silently resume into it — the user
  // most likely abandoned an earlier onboarding attempt. If it does have
  // evaluations, fall through to the normal error UI so the user can decide.
  async function tryResumeExisting(existingProjectId) {
    try {
      const info = await getProjectInfo(existingProjectId);
      if (info.runsCount > 0) return false;
      // Timeout so a backend that accepts but never responds cannot stall
      // the resume flow; the catch below falls back to the normal error UI.
      const scanRes = await fetch(`/api/projects/${encodeURIComponent(existingProjectId)}/scan`, {
        signal: AbortSignal.timeout(120000),
      });
      if (!scanRes.ok) return false;
      const scanData = await scanRes.json();
      actions.succeedScan(existingProjectId, scanData);
      return true;
    } catch {
      return false;
    }
  }

  async function handleSubmit() {
    const repo = state.repo.value?.trim();
    if (!repo) return;
    if (URL_RE.test(repo)) {
      // URL input branches into the clone-target sub-step. Local-path inputs
      // continue to call createProject directly.
      setSubStep('cloneTarget');
      setCloneError(null);
      return;
    }
    actions.startScan();
    try {
      const { projectId, scanData } = await createProject({ repo });
      actions.succeedScan(projectId, scanData);
    } catch (err) {
      if (err.status === 409 && err.existingProjectId) {
        const resumed = await tryResumeExisting(err.existingProjectId);
        if (resumed) return;
      }
      actions.failScan({ message: err.message, status: err.status, existingProjectId: err.existingProjectId });
    }
  }

  async function handleCloneTargetSubmit({ cloneDest, ephemeral }) {
    const repo = state.repo.value?.trim();
    setCloneSubmitting(true);
    setCloneError(null);
    actions.startScan();
    try {
      const payload = { repo, cloneDest, ephemeral };
      const { projectId, scanData } = await createProject(payload);
      if (cloneDest && !ephemeral) {
        try { localStorage.setItem(CLONE_DEST_STORAGE_KEY, cloneDest); } catch (_) { /* private mode */ }
      }
      actions.succeedScan(projectId, scanData);
      setSubStep('input');
    } catch (err) {
      if (err.status === 409 && err.existingProjectId) {
        const resumed = await tryResumeExisting(err.existingProjectId);
        if (resumed) {
          setSubStep('input');
          return;
        }
      }
      setCloneError(friendlyCloneError(err));
      actions.failScan({ message: err.message, status: err.status, existingProjectId: err.existingProjectId, code: err.code });
    } finally {
      setCloneSubmitting(false);
    }
  }

  function handleFolderSelect(path) {
    actions.setRepo({ value: path, source: 'local' });
    setFolderBrowserOpen(false);
  }

  if (subStep === 'cloneTarget') {
    return (
      <CloneTargetStep
        repoUrl={state.repo.value?.trim()}
        onSubmit={handleCloneTargetSubmit}
        onBack={() => { setSubStep('input'); setCloneError(null); }}
        submitting={cloneSubmitting}
        error={cloneError}
        stepIndex={stepIndex}
        stepTotal={stepTotal}
      />
    );
  }

  return (
    <div className="onboarding-step onboarding-step--repo-scan">
      <TermHeader name="repo" sub={`step ${stepIndex} of ${stepTotal} · paste a url or local folder`} />
      <p className="onboarding-step__pitch">
        Paste a Git URL or pick a local folder. quodeq will scan it locally. No AI tokens used yet.
      </p>

      <div className={sub === 'idle' ? 'onboarding-repo-row' : 'onboarding-repo-row onboarding-form-locked'}>
        <TermInput
          prompt="$"
          command="repo"
          value={state.repo.value}
          onChange={(value) => actions.setRepo({ value, source: 'url' })}
          onSubmit={handleSubmit}
          placeholder="git@github.com:org/repo.git"
          ariaLabel="repository url or local path"
        />
        <button
          type="button"
          className="term-btn--secondary onboarding-repo-row__browse"
          onClick={() => setFolderBrowserOpen(true)}
          disabled={sub !== 'idle'}
        >
          local
        </button>
      </div>
      {sub === 'scanned' && (
        <button type="button" className="onboarding-edit-link" onClick={actions.resetScan}>edit repository</button>
      )}

      {sub === 'scanning' && (
        <div className="onboarding-scan-progress">
          <ScanProgress />
          <p className="onboarding-scan-progress__hint">cloning · walking files · detecting languages…</p>
        </div>
      )}

      {sub === 'error' && (
        <div className="onboarding-scan-error" role="alert">
          <p>{state.scanError?.message || 'Scan failed.'}</p>
          <div className="onboarding-step__actions">
            <button type="button" className="term-btn--primary" onClick={handleSubmit}>try again</button>
            <button type="button" className="term-btn--secondary" onClick={actions.resetScan}>edit repository</button>
          </div>
        </div>
      )}

      {sub === 'scanned' && (() => {
        const totalFiles = state.scan?.total_files ?? 0;
        const codeFiles = state.scan?.code_files ?? 0;
        const langs = state.scan?.languages || {};
        const langCount = Object.keys(langs).length;
        const branchCount = state.scan?.branches?.length ?? 0;
        const topLangs = Object.entries(langs).sort((a, b) => b[1] - a[1]).slice(0, 8);
        return (
          <div className="onboarding-scan-summary">
            <StatStrip cards>
              <Stat label="FILES" value={totalFiles} hint="all files in repo" />
              <Stat label="CODE" value={codeFiles} hint="files the eval will analyse" />
              <Stat label="LANGUAGES" value={langCount} />
              <Stat label="BRANCHES" value={branchCount} />
            </StatStrip>
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
          <button type="button" className="term-btn term-btn--primary term-btn--filled" onClick={handleSubmit} disabled={!state.repo.value}>scan repository</button>
        )}
        {sub === 'scanned' && (
          <button type="button" className="term-btn term-btn--primary term-btn--filled" onClick={onContinue}>continue</button>
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
