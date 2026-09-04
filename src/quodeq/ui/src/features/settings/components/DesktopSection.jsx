import { useEffect, useState } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';

function MenubarRow({ enabled, onToggle }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label">{t('settings.menubarToggle')}</span>
        <span className="settings-description">{t('settings.menubarToggleDesc')}</span>
      </div>
      <div className="settings-pill-group">
        <button
          type="button"
          className={`settings-pill${enabled ? ' settings-pill--active' : ''}`}
          onClick={() => onToggle(true)}
          aria-pressed={enabled}
        >
          {t('settings.on')}
        </button>
        <button
          type="button"
          className={`settings-pill${!enabled ? ' settings-pill--active' : ''}`}
          onClick={() => onToggle(false)}
          aria-pressed={!enabled}
        >
          {t('settings.off')}
        </button>
      </div>
    </div>
  );
}

export default function DesktopSection() {
  const { getMenubar, setMenubar } = useApi();
  const [status, setStatus] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getMenubar()
      .then((data) => { if (!cancelled) setStatus(data); })
      .catch(() => { /* unsupported or unreachable: section stays hidden */ });
    return () => { cancelled = true; };
  }, [getMenubar]);

  if (!status?.supported) return null;

  const onToggle = async (enabled) => {
    const previous = status;
    setStatus((s) => ({ ...(s || {}), enabled }));
    try {
      setStatus(await setMenubar(enabled));
    } catch {
      setStatus(previous); // fail-silent revert
    }
  };

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.desktopLabel')}</SectionLabel>
      </div>
      <MenubarRow enabled={!!status.enabled} onToggle={onToggle} />
    </section>
  );
}
