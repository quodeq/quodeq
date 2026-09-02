import { useEffect, useState } from 'react';
import { terminalStatus } from '../../../api/terminal.js';
import { t } from '../../../strings/index.js';

/**
 * TerminalPane.jsx's terminal-availability check (enabled/reason/shell),
 * extracted verbatim.
 */
export function useTerminalPaneStatus() {
  const [reason, setReason] = useState(null);
  const [checked, setChecked] = useState(false);
  const [shell, setShell] = useState('');

  useEffect(() => {
    let alive = true;
    terminalStatus().then((s) => {
      if (!alive) return;
      setReason(s.enabled ? null : s.reason);
      setShell(s.shell || '');
      setChecked(true);
    }).catch(() => { if (alive) { setReason(t('terminal.unavailable')); setChecked(true); } });
    return () => { alive = false; };
  }, []);

  return { reason, checked, shell };
}
