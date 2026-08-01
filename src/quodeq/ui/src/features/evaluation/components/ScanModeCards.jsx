import { useEffect } from 'react';
import HelpHint from '../../../components/HelpHint.jsx';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { t } from '../../../strings/index.js';

const STORAGE_KEY = 'quodeq.cleanScan.permanent';

function readPermanent() {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function writePermanent(on) {
  try {
    if (on) localStorage.setItem(STORAGE_KEY, '1');
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore quota / disabled storage */
  }
}

function ModeCard({ id, checked, onPick, disabled, title, tag, children }) {
  // The explanation lives behind the app's "?" hint, top-right of the card.
  // A button inside a <label> is excluded from label activation, so opening
  // the hint does not also pick the radio.
  return (
    <label className={`eval-mode-card${checked ? ' eval-mode-card--selected' : ''}${disabled ? ' eval-mode-card--disabled' : ''}`}>
      <input
        type="radio"
        name="scan-mode"
        value={id}
        checked={checked}
        onChange={onPick}
        disabled={disabled}
        className="eval-mode-card__input"
      />
      <span className="eval-mode-card__dot" aria-hidden="true"><span /></span>
      <span className="eval-mode-card__body">
        <span className="eval-mode-card__title-row">
          <span className="eval-mode-card__title">{title}</span>
          <span className="eval-mode-card__tag">{tag}</span>
          <span className="eval-mode-card__hint">
            <HelpHint label={t('evaluate.aboutTitle', { title })}>{children}</HelpHint>
          </span>
        </span>
      </span>
    </label>
  );
}

/**
 * Scan-mode radio cards: incremental vs clean scan. Same tri-state contract
 * as the old CleanScanToggle — `value` is 'off' | 'once' | 'permanent' —
 * so `buildScanPayload`'s cleanScan mapping and the one-shot "once"
 * consumption in `useDimensionSelection` are untouched. Picking clean
 * reveals a "this scan only / always" sub-choice; "always" persists to
 * localStorage exactly like before.
 */
export default function ScanModeCards({ value, onChange, disabled = false }) {
  const { showToast } = useSidePane();

  useEffect(() => {
    // First mount: hydrate 'permanent' from localStorage so the cards reflect
    // the user's saved preference. Only when the parent passes 'off' as the
    // initial value (no in-flight 'once' state to clobber).
    if (value === 'off' && readPermanent()) onChange('permanent');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isClean = value !== 'off';

  function pickIncremental() {
    writePermanent(false);
    onChange('off');
  }
  function pickClean() {
    // Default to one-shot; "always" is the explicit sub-choice.
    if (isClean) return;
    onChange('once');
    // Auto-dismissing heads-up: switching to clean is easy to underestimate.
    showToast(t('evaluate.cleanScanToast'));
  }
  function pickOnce() {
    writePermanent(false);
    onChange('once');
  }
  function pickPermanent() {
    writePermanent(true);
    onChange('permanent');
  }

  return (
    <div className="eval-scan-mode">
      <div className="eval-scan-mode__head">
        <span className="eval-scan-mode__label">{t('evaluate.scanModeLabel')}</span>
        {isClean && (
          <span className="eval-scan-mode__persist">
            <span className="eval-scan-mode__persist-label">{t('evaluate.applyCleanTo')}</span>
            <span className="eval-scan-mode__seg" role="group" aria-label={t('evaluate.cleanPersistAria')}>
              <button
                type="button"
                className={`eval-scan-mode__seg-btn${value === 'once' ? ' eval-scan-mode__seg-btn--on' : ''}`}
                onClick={pickOnce}
                disabled={disabled}
                aria-pressed={value === 'once'}
              >
                {t('evaluate.thisScanOnly')}
              </button>
              <button
                type="button"
                className={`eval-scan-mode__seg-btn${value === 'permanent' ? ' eval-scan-mode__seg-btn--on' : ''}`}
                onClick={pickPermanent}
                disabled={disabled}
                aria-pressed={value === 'permanent'}
                title={t('evaluate.alwaysTitle')}
              >
                {t('evaluate.always')}
              </button>
            </span>
          </span>
        )}
      </div>
      <div className="eval-scan-mode__grid">
        <ModeCard id="incremental" checked={!isClean} onPick={pickIncremental} disabled={disabled} title={t('evaluate.incremental')} tag={t('evaluate.recommended')}>
          {t('evaluate.incrementalDesc')}
        </ModeCard>
        <ModeCard id="clean" checked={isClean} onPick={pickClean} disabled={disabled} title={t('evaluate.cleanScanTitle')} tag={t('evaluate.slow')}>
          {t('evaluate.cleanScanDesc')}
        </ModeCard>
      </div>
      {value === 'permanent' && (
        <div className="eval-scan-mode__note">
          <span className="eval-scan-mode__note-glyph" aria-hidden="true">▸</span>
          {t('evaluate.permanentNote')}
        </div>
      )}
    </div>
  );
}
