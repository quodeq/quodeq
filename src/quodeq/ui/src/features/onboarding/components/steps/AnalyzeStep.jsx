import { TermHeader, TermInput } from '../../../../components/terminal/index.js';
import { t } from '../../../../strings/index.js';
import { REPO_SOURCE } from '../../onboardingVocab.js';
import { useAnalyzeForm } from '../../hooks/useAnalyzeForm.js';
import { useAnalyzeLaunch } from '../../hooks/useAnalyzeLaunch.js';
import WorkingCopyNote from '../analyze/WorkingCopyNote.jsx';
import AddProblem from '../analyze/AddProblem.jsx';

// `locked` while a registration runs: the repository must not change under it.
function RepositoryBlock({ form, locked }) {
  const { workingCopy } = form;
  const typed = form.repo.trim();
  return (
    <section className="analyze-block">
      <h3 className="analyze-block__title">{t('onboarding.yourRepository')}</h3>
      <p className="analyze-block__hint">{t('onboarding.repoHint')}</p>
      <div className="analyze-block__row analyze-repo-row">
        <span className="repo-form__field analyze-repo-row__field">
          <TermInput command="repo" value={form.repo} onChange={form.setRepo} ariaLabel={t('onboarding.repoAria')} placeholder={t('onboarding.repoPlaceholder')} disabled={locked} />
        </span>
        <button type="button" className="term-btn term-btn--secondary" onClick={form.browseRepoFolder} disabled={locked}>
          {t('onboarding.localFolder')}
        </button>
      </div>
      {typed && form.source === REPO_SOURCE.FOLDER && <p className="analyze-block__hint">{t('onboarding.folderHint')}</p>}
      {typed && form.source === REPO_SOURCE.URL && (
        <WorkingCopyNote
          path={workingCopy.path}
          onChange={workingCopy.change}
          onReset={workingCopy.changed ? workingCopy.reset : undefined}
        />
      )}
    </section>
  );
}

/**
 * The add panel: one field for a git url or a local folder (the `local
 * folder` button fills it from the picker), and where a url's working copy
 * goes. `add` registers the repository (useAnalyzeLaunch: a folder at once,
 * a url as a clone job the Repositories tile follows) and hands `onAdded`
 * `{ projectId, cloning }`; the panel closes on it. Who reviews the project
 * and against what is decided on Evaluate, not here.
 */
export default function AnalyzeStep({ state, actions, onAdded }) {
  const wizard = { ...actions, state };
  const form = useAnalyzeForm({ wizard });
  const add = useAnalyzeLaunch({ wizard, form, onAdded });
  return (
    <div className="onboarding-step onboarding-step--analyze">
      <TermHeader name={t('onboarding.termAddProject')} sub={t('onboarding.subAddProject')} />
      <RepositoryBlock form={form} locked={add.busy} />
      <AddProblem add={add} url={form.repo.trim()} />
      <div className="onboarding-step__actions onboarding-step__actions--end">
        <button type="button" className="term-btn term-btn--primary term-btn--filled" disabled={!form.canSubmit || add.busy} onClick={add.run}>
          {add.busy ? t('onboarding.adding') : t('onboarding.addButton')}
        </button>
      </div>
      {form.pickers.repo}
      {form.pickers.workingCopy}
    </div>
  );
}
