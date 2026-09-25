import { t } from '../../../strings/index.js';

/**
 * The provider picker's pill tabs: one pill per AI client, the active one
 * selected and the uninstalled ones marked disabled with an explanatory
 * title.
 * @param {Object} props
 * @param {Array<{id: string, label: string, installed?: boolean}>} props.clients
 * @param {string} props.activeId Id of the selected client.
 * @param {(id: string) => void} props.onSelect
 * @param {boolean} [props.selectUninstalled=false] Also report clicks on
 *   uninstalled clients (the analysis picker shows their install hint).
 */
export function ProviderPillGroup({ clients, activeId, onSelect, selectUninstalled = false }) {
  return (
    <div className="settings-pill-group" role="tablist">
      {clients.map((c) => {
        const installed = c.installed !== false;
        return (
          <button
            key={c.id}
            type="button"
            role="tab"
            aria-selected={c.id === activeId}
            aria-disabled={!installed}
            title={installed ? undefined : t('settings.providerNotInstalledTitle', { name: c.label })}
            className={`settings-pill${c.id === activeId ? ' settings-pill--active' : ''}${installed ? '' : ' settings-pill--disabled'}`}
            onClick={() => { if (!installed && !selectUninstalled) return; onSelect(c.id); }}
          >
            {c.label}
          </button>
        );
      })}
    </div>
  );
}
