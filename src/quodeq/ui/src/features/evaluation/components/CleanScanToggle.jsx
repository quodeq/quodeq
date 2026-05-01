import { useEffect, useState } from 'react';

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
            ? 'Clean scan: always (click to disable)'
            : value === 'once'
              ? 'Clean scan: just this scan (click to disable)'
              : 'Clean scan: drops carry-forward; every file goes through the LLM again'
        }
        aria-pressed={isOn}
      >
        Clean scan
        {value === 'permanent' && <span className="clean-scan-toggle__dot" aria-hidden="true" />}
      </button>

      {confirmOpen && (
        <div className="qd-confirm-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) cancel(); }}>
          <div className="qd-confirm-dialog">
            <h3 className="qd-confirm-title">Clean scan</h3>
            <div className="qd-confirm-message">
              <p>Reanalyze every file from scratch. Slower than a normal scan, but findings will reflect your current standards and settings.</p>
              <p>Use this after you change a standard, or whenever you want a fresh second opinion.</p>
            </div>
            <div className="qd-confirm-actions clean-scan-confirm-actions">
              <button type="button" className="qd-confirm-btn qd-confirm-btn--cancel" onClick={cancel}>Cancel</button>
              <button type="button" className="qd-confirm-btn qd-confirm-btn--confirm" onClick={pickOnce}>Just this scan</button>
              <button type="button" className="qd-confirm-btn qd-confirm-btn--confirm qd-confirm-btn--danger" onClick={pickPermanent}>
                Always <span className="clean-scan-confirm-meta">(all projects)</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
