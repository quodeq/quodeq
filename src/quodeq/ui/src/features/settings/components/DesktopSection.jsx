import { useEffect, useState } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';
import { SettingsOnOffPills } from './settingsRowParts.jsx';

function MenubarRow({ enabled, onToggle }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label">{t('settings.menubarToggle')}</span>
        <span className="settings-description">{t('settings.menubarToggleDesc')}</span>
      </div>
      <SettingsOnOffPills on={enabled} onToggle={onToggle} />
    </div>
  );
}

export default function DesktopSection() {
  const { getMenubar, setMenubar } = useApi();
  const [status, setStatus] = useState(null);
  const [toggleError, setToggleError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getMenubar()
      .then((data) => { if (!cancelled) setStatus(data); })
      .catch((err) => {
        console.warn('[DesktopSection] getMenubar failed:', err); // unsupported or unreachable: section stays hidden
      });
    return () => { cancelled = true; };
  }, [getMenubar]);

  if (!status?.supported) return null;

  const onToggle = async (enabled) => {
    const previous = status;
    setStatus((s) => ({ ...(s || {}), enabled }));
    setToggleError(null);
    try {
      setStatus(await setMenubar(enabled));
    } catch (err) {
      console.warn('[DesktopSection] setMenubar failed:', err);
      setStatus(previous); // revert the optimistic toggle
      setToggleError(t('settings.menubarToggleFailed'));
    }
  };

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.desktopLabel')}</SectionLabel>
      </div>
      <MenubarRow enabled={!!status.enabled} onToggle={onToggle} />
      {toggleError && <div className="settings-row"><span className="settings-error">{toggleError}</span></div>}
    </section>
  );
}
