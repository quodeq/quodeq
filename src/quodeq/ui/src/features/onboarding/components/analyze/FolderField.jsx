import { t } from '../../../../strings/index.js';

/**
 * The folder source of a url-or-folder form: the picked path (or "no folder
 * chosen yet") and `choose a folder`, which opens the folder browser. Shared
 * by the evaluations repository form and the analyze screen.
 *
 * @param {object} props
 * @param {string} props.folderPath - the picked path, '' while none
 * @param {() => void} props.onPick
 * @param {boolean} [props.disabled]
 */
export default function FolderField({ folderPath, onPick, disabled = false }) {
  return (
    <span className="repo-form__field repo-form__folder">
      <span className={`repo-form__path${folderPath ? '' : ' repo-form__path--empty'}`}>
        {folderPath || t('onboarding.noFolderYet')}
      </span>
      <button type="button" className="term-btn term-btn--secondary" onClick={onPick} disabled={disabled}>
        {t('onboarding.chooseFolder')}
      </button>
    </span>
  );
}
