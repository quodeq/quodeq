import { TermHeader, TermInput } from '../../../../components/terminal/index.js';
import ScanProgress from '../../../evaluation/components/ScanProgress.jsx';
import FolderBrowser from '../../../evaluation/components/FolderBrowser.jsx';
import CloneTargetStep from './CloneTargetStep.jsx';
import { RepoScanSummary } from './RepoScanSummary.jsx';
import { useRepoScanStep } from '../../hooks/useRepoScanStep.js';
import { t } from '../../../../strings/index.js';

function RepoScanInputRow({ sub, state, actions, handleSubmit, setFolderBrowserOpen }) {
  return (
    <div className={sub === 'idle' ? 'onboarding-repo-row' : 'onboarding-repo-row onboarding-form-locked'}>
      <TermInput
        prompt="$"
        command="repo"
        value={state.repo.value}
        onChange={(value) => actions.setRepo({ value, source: 'url' })}
        onSubmit={handleSubmit}
        placeholder="git@github.com:org/repo.git"
        ariaLabel={t('onboarding.repoInputAria')}
      />
      <button
        type="button"
        className="term-btn--secondary onboarding-repo-row__browse"
        onClick={() => setFolderBrowserOpen(true)}
        disabled={sub !== 'idle'}
      >
        {t('onboarding.local')}
      </button>
    </div>
  );
}

function RepoScanStatusSection({ sub, state, actions, handleSubmit }) {
  return (
    <>
      {sub === 'scanned' && (
        <button type="button" className="onboarding-edit-link" onClick={actions.resetScan}>{t('onboarding.editRepository')}</button>
      )}

      {sub === 'scanning' && (
        <div className="onboarding-scan-progress">
          <ScanProgress />
          <p className="onboarding-scan-progress__hint">{t('onboarding.scanning')}</p>
        </div>
      )}

      {sub === 'error' && (
        <div className="onboarding-scan-error" role="alert">
          <p>{state.scanError?.message || t('onboarding.scanFailed')}</p>
          <div className="onboarding-step__actions">
            <button type="button" className="term-btn--primary" onClick={handleSubmit}>{t('onboarding.tryAgain')}</button>
            <button type="button" className="term-btn--secondary" onClick={actions.resetScan}>{t('onboarding.editRepository')}</button>
          </div>
        </div>
      )}

      {sub === 'scanned' && <RepoScanSummary scan={state.scan} />}
    </>
  );
}

function RepoScanFooterActions({ sub, state, handleSubmit, onContinue, folderBrowserOpen, setFolderBrowserOpen, handleFolderSelect }) {
  return (
    <>
      <div className="onboarding-step__actions">
        {sub === 'idle' && (
          <button type="button" className="term-btn term-btn--primary term-btn--filled" onClick={handleSubmit} disabled={!state.repo.value}>{t('onboarding.scanRepository')}</button>
        )}
        {sub === 'scanned' && (
          <button type="button" className="term-btn term-btn--primary term-btn--filled" onClick={onContinue}>{t('common.continue')}</button>
        )}
      </div>

      {folderBrowserOpen && (
        <FolderBrowser
          onSelect={handleFolderSelect}
          onClose={() => setFolderBrowserOpen(false)}
          title={t('onboarding.selectFolderOrFile')}
          confirmText={t('onboarding.useThisPath')}
          showFiles
        />
      )}
    </>
  );
}

export default function RepoScanStep({ state, actions, createProject, getProjectInfo, getProjectScan, onContinue, onCancel, stepIndex = 0, stepTotal = 0 }) {
  const sub = state.repoScanSubState;
  const {
    folderBrowserOpen, setFolderBrowserOpen,
    subStep, setSubStep,
    cloneSubmitting, cloneError, setCloneError,
    handleSubmit, handleCloneTargetSubmit, handleFolderSelect,
  } = useRepoScanStep({ state, actions, createProject, getProjectInfo, getProjectScan });

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
      <TermHeader name={t('onboarding.termRepo')} sub={t('onboarding.subRepo', { step: stepIndex, total: stepTotal })} />
      <p className="onboarding-step__pitch">
        {t('onboarding.repoScanDesc')}
      </p>

      <RepoScanInputRow sub={sub} state={state} actions={actions} handleSubmit={handleSubmit} setFolderBrowserOpen={setFolderBrowserOpen} />
      <RepoScanStatusSection sub={sub} state={state} actions={actions} handleSubmit={handleSubmit} />
      <RepoScanFooterActions
        sub={sub} state={state} handleSubmit={handleSubmit} onContinue={onContinue}
        folderBrowserOpen={folderBrowserOpen} setFolderBrowserOpen={setFolderBrowserOpen} handleFolderSelect={handleFolderSelect}
      />
    </div>
  );
}
