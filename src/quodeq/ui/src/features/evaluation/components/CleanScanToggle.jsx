import { useEffect, useState } from 'react';
import { t } from '../../../strings/index.js';
import { readString, removeKey, writeString } from '../../../adapters/storage.js';

const STORAGE_KEY = 'quodeq.cleanScan.permanent';

function readPermanent(storage) {
  return readString(STORAGE_KEY, null, storage) === '1';
}

function writePermanent(on, storage) {
  if (on) writeString(STORAGE_KEY, '1', storage);
  else removeKey(STORAGE_KEY, storage);
}

/**
 * Tri-state Clean Scan toggle. State is one of:
 *  - 'off'        — incremental mode (default)
 *  - 'once'       — clean for next scan only; resets to 'off' after submit
 *  - 'permanent'  — clean for every scan; persisted to localStorage
 *
 * `value` is the current state, `onChange` receives the new state. When the
 * toggle is off and the user clicks it, a popup asks whether to enable for
 * one scan, always, or cancel.
 */
export default function CleanScanToggle({ value, onChange, disabled = false }) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    // First mount: hydrate 'permanent' from localStorage so the toggle reflects
    // the user's saved preference. We only do this when the parent passes
    // 'off' as the initial value (no in-flight 'once' state to clobber).
    if (value === 'off' && readPermanent()) onChange('permanent');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isOn = value === 'once' || value === 'permanent';

  function handleClick() {
    if (disabled) return;
    if (isOn) {
      // Turning off: clear localStorage too, regardless of which 'on' state.
      writePermanent(false);
      onChange('off');
      return;
    }
    setConfirmOpen(true);
  }

  function pickOnce() {
    setConfirmOpen(false);
    onChange('once');
  }
  function pickPermanent() {
    setConfirmOpen(false);
    writePermanent(true);
    onChange('permanent');
  }
  function cancel() {
    setConfirmOpen(false);
  }

  return (
    <>
      <button
        type="button"
        className={`clean-scan-toggle${isOn ? ' clean-scan-toggle--on' : ''}${value === 'permanent' ? ' clean-scan-toggle--permanent' : ''}`}
        onClick={handleClick}
        disabled={disabled}
        title={
          value === 'permanent'
            ? t('evaluate.cleanAlwaysTitle')
            : value === 'once'
              ? t('evaluate.cleanOnceTitle')
              : t('evaluate.cleanOffTitle')
        }
        aria-pressed={isOn}
      >
        {t('evaluate.cleanScan')}
        {value === 'permanent' && <span className="clean-scan-toggle__dot" aria-hidden="true" />}
      </button>

      {confirmOpen && (
        <div className="qd-confirm-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) cancel(); }}>
          <div className="qd-confirm-dialog">
            <h3 className="qd-confirm-title">{t('evaluate.cleanScan')}</h3>
            <div className="qd-confirm-message">
              <p>{t('evaluate.cleanDialogP1')}</p>
              <p>{t('evaluate.cleanDialogP2')}</p>
            </div>
            <div className="qd-confirm-actions clean-scan-confirm-actions">
              <button type="button" className="qd-confirm-btn qd-confirm-btn--cancel" onClick={cancel}>{t('common.cancel')}</button>
              <button type="button" className="qd-confirm-btn qd-confirm-btn--confirm" onClick={pickOnce}>{t('evaluate.justThisScan')}</button>
              <button type="button" className="qd-confirm-btn qd-confirm-btn--confirm qd-confirm-btn--danger" onClick={pickPermanent}>
                {t('evaluate.alwaysCap')} <span className="clean-scan-confirm-meta">{t('evaluate.allProjects')}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
