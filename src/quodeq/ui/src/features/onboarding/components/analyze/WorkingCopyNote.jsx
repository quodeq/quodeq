import { t } from '../../../../strings/index.js';

/**
 * Under a pasted url: where quodeq keeps its working copy of the repository,
 * with `change` to pick another root folder and, once changed, a way back to
 * the default.
 *
 * @param {object} props
 * @param {string} props.path - the working copy's folder (root plus repository name)
 * @param {() => void} props.onChange
 * @param {() => void} [props.onReset] - shown only when given (the root was changed)
 */
export default function WorkingCopyNote({ path, onChange, onReset }) {
  return (
    <p className="analyze-working-copy">
      <span className="analyze-working-copy__text">{t('onboarding.workingCopy', { path })}</span>
      <button type="button" className="onboarding-edit-link" aria-label={t('onboarding.changeWorkingCopy')} onClick={onChange}>
        {t('onboarding.change')}
      </button>
      {onReset && (
        <button type="button" className="onboarding-edit-link" onClick={onReset}>{t('onboarding.useDefaultFolder')}</button>
      )}
    </p>
  );
}
