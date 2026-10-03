import { useRef } from 'react';
import { t } from '../../../../strings/index.js';
import { KEY } from '../../../../vocab/keyboard.js';
import { REPO_SOURCE } from '../../onboardingVocab.js';

const ORDER = [REPO_SOURCE.URL, REPO_SOURCE.FOLDER];
const STEP_BY_KEY = { [KEY.ARROW_LEFT]: -1, [KEY.ARROW_UP]: -1, [KEY.ARROW_RIGHT]: 1, [KEY.ARROW_DOWN]: 1 };

/**
 * The url-or-folder segmented switch of the repository forms (the connect
 * step's evaluations repository, the analyze step's repository). A
 * radiogroup: one tab stop on the picked source, arrow keys move between
 * the two the way native radios do.
 *
 * @param {object} props
 * @param {'url'|'folder'} props.value - the picked source (REPO_SOURCE)
 * @param {(source: string) => void} props.onChange
 * @param {{ url?: string, folder?: string }} [props.labels] - overrides the default copy
 */
export default function RepoSourceSwitch({ value, onChange, labels }) {
  const refs = useRef({});
  const text = {
    [REPO_SOURCE.URL]: labels?.url ?? t('onboarding.sourceUrl'),
    [REPO_SOURCE.FOLDER]: labels?.folder ?? t('onboarding.sourceFolder'),
  };
  const onKeyDown = (e) => {
    const step = STEP_BY_KEY[e.key];
    if (!step) return;
    e.preventDefault();
    const next = ORDER[(ORDER.indexOf(value) + step + ORDER.length) % ORDER.length];
    onChange(next);
    refs.current[next]?.focus();
  };
  return (
    <div className="repo-source-switch" role="radiogroup" aria-label={t('onboarding.sourceAria')}>
      {ORDER.map((source) => (
        <button
          key={source}
          ref={(el) => { refs.current[source] = el; }}
          type="button"
          role="radio"
          aria-checked={value === source}
          tabIndex={value === source ? 0 : -1}
          className={`repo-source-switch__option${value === source ? ' repo-source-switch__option--active' : ''}`}
          onClick={() => onChange(source)}
          onKeyDown={onKeyDown}
        >
          {text[source]}
        </button>
      ))}
    </div>
  );
}
