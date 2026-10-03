import { TermHeader, TermInput } from '../../../../components/terminal/index.js';
import { t } from '../../../../strings/index.js';
import { REPO_SOURCE } from '../../onboardingVocab.js';
import { useAnalyzeForm } from '../../hooks/useAnalyzeForm.js';
import { useAnalyzeLaunch } from '../../hooks/useAnalyzeLaunch.js';
import RepoSourceSwitch from '../analyze/RepoSourceSwitch.jsx';
import FolderField from '../analyze/FolderField.jsx';
import WorkingCopyNote from '../analyze/WorkingCopyNote.jsx';
import ReviewedByRow from '../analyze/ReviewedByRow.jsx';
import AgainstRow from '../analyze/AgainstRow.jsx';
import CloneProgress from '../analyze/CloneProgress.jsx';

// `locked` while a clone or registration runs: the repository being cloned
// must not change under it.
function RepositoryBlock({ form, locked }) {
  const { workingCopy } = form;
  return (
    <section className="analyze-block">
      <h3 className="analyze-block__title">{t('onboarding.yourRepository')}</h3>
      <p className="analyze-block__hint">{t('onboarding.repoHint')}</p>
      <RepoSourceSwitch value={form.source} onChange={form.setSource} disabled={locked} />
      <div className="analyze-block__row">
        {form.source === REPO_SOURCE.URL ? (
          <span className="repo-form__field">
            <TermInput command="repo" value={form.repo} onChange={form.setRepo} ariaLabel={t('onboarding.repoAria')} placeholder={t('onboarding.repoPlaceholder')} disabled={locked} />
          </span>
        ) : (
          <FolderField folderPath={form.repo} onPick={form.browseRepoFolder} disabled={locked} />
        )}
      </div>
      {form.source === REPO_SOURCE.URL && form.repo.trim() && (
        <WorkingCopyNote
          path={workingCopy.path}
          onChange={workingCopy.change}
          onReset={workingCopy.changed ? workingCopy.reset : undefined}
        />
      )}
    </section>
  );
}

function ReviewSummary({ form }) {
  return (
    <p className="analyze-summary">
      <span className="analyze-summary__text">
        {t('onboarding.reviewSummary', { provider: form.provider.label, standard: form.standard.name })}
      </span>
      <button type="button" className="onboarding-edit-link" onClick={form.expand}>{t('onboarding.change')}</button>
    </p>
  );
}

/**
 * The one analyze screen: the repository (a git url or a local folder, with
 * where its working copy goes), who reviews it and against which standard.
 * A returning user (a provider configured) sees the last two as one summary
 * line with `change`. `detect` is injectable for tests.
 *
 * `scan and run` registers the repository (useAnalyzeLaunch: a folder at
 * once, a url as a clone job shown in CloneProgress) and hands `onLaunch`
 * `{ projectId, standardIds }` when the project is there.
 */
export default function AnalyzeStep({ state, actions, standards, detect, onLaunch }) {
  const wizard = { ...actions, state };
  const form = useAnalyzeForm({ wizard, standards, detect });
  const launch = useAnalyzeLaunch({ wizard, form, onLaunch });
  return (
    <div className="onboarding-step onboarding-step--analyze">
      <TermHeader name={t('onboarding.termAnalyze')} sub={t('onboarding.subAnalyze')} />
      <RepositoryBlock form={form} locked={launch.busy} />
      {form.collapsed
        // The summary names the standard: it waits for the list to load.
        ? form.standard.ready && <ReviewSummary form={form} />
        : (
          <>
            <ReviewedByRow provider={form.provider} />
            <AgainstRow standard={form.standard} standards={standards} />
          </>
        )}
      <CloneProgress launch={launch} url={form.repo.trim()} />
      <div className="onboarding-step__actions">
        <button type="button" className="term-btn term-btn--primary term-btn--filled" disabled={!form.canSubmit || launch.busy} onClick={launch.run}>
          {t('onboarding.scanAndRun')}
        </button>
      </div>
      {form.pickers.repo}
      {form.pickers.workingCopy}
    </div>
  );
}
