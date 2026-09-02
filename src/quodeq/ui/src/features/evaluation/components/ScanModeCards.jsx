import { useEffect } from 'react';
import HelpHint from '../../../components/HelpHint.jsx';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { t } from '../../../strings/index.js';
import { readPermanent, writePermanent } from './scanModePersistence.js';

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

// mode is one of: 'incremental' | 'clean' (the two radio cards) or
// 'once' | 'permanent' (the clean-scan persistence sub-choice). Picking
// clean defaults to one-shot; "always" is the explicit sub-choice.
function makeHandlePick({ isClean, onChange, showToast }) {
  return function handlePick(mode) {
    if (mode === 'clean') {
      if (isClean) return;
      onChange('once');
      // Auto-dismissing heads-up: switching to clean is easy to underestimate.
      showToast(t('evaluate.cleanScanToast'));
      return;
    }
    if (mode === 'incremental') {
      writePermanent(false);
      onChange('off');
      return;
    }
    writePermanent(mode === 'permanent');
    onChange(mode);
  };
}

function PersistToggle({ value, onPick, disabled }) {
  return (
    <span className="eval-scan-mode__persist">
      <span className="eval-scan-mode__persist-label">{t('evaluate.applyCleanTo')}</span>
      <span className="eval-scan-mode__seg" role="group" aria-label={t('evaluate.cleanPersistAria')}>
        <button
          type="button"
          className={`eval-scan-mode__seg-btn${value === 'once' ? ' eval-scan-mode__seg-btn--on' : ''}`}
          onClick={() => onPick('once')}
          disabled={disabled}
          aria-pressed={value === 'once'}
        >
          {t('evaluate.thisScanOnly')}
        </button>
        <button
          type="button"
          className={`eval-scan-mode__seg-btn${value === 'permanent' ? ' eval-scan-mode__seg-btn--on' : ''}`}
          onClick={() => onPick('permanent')}
          disabled={disabled}
          aria-pressed={value === 'permanent'}
          title={t('evaluate.alwaysTitle')}
        >
          {t('evaluate.always')}
        </button>
      </span>
    </span>
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
  const handlePick = makeHandlePick({ isClean, onChange, showToast });

  return (
    <div className="eval-scan-mode">
      <div className="eval-scan-mode__head">
        <span className="eval-scan-mode__label">{t('evaluate.scanModeLabel')}</span>
        {isClean && <PersistToggle value={value} onPick={handlePick} disabled={disabled} />}
      </div>
      <div className="eval-scan-mode__grid">
        <ModeCard id="incremental" checked={!isClean} onPick={() => handlePick('incremental')} disabled={disabled} title={t('evaluate.incremental')} tag={t('evaluate.recommended')}>
          {t('evaluate.incrementalDesc')}
        </ModeCard>
        <ModeCard id="clean" checked={isClean} onPick={() => handlePick('clean')} disabled={disabled} title={t('evaluate.cleanScanTitle')} tag={t('evaluate.slow')}>
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
