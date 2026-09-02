import { t } from '../strings/index.js';

/**
 * TopBar.jsx's provider/model pill (button variant when onProviderClick is
 * set, plain span otherwise). Extracted verbatim.
 */
export function TopBarProviderPill({ provider, model, onProviderClick }) {
  if (!provider && !model) return null;
  if (!onProviderClick) {
    return (
      <span className="topbar-pill">
        {provider && <span>{provider}</span>}
        {provider && model && <span className="topbar-pill-sep">·</span>}
        {model && <span className="topbar-pill-muted">{model}</span>}
      </span>
    );
  }
  return (
    <button
      type="button"
      className="topbar-pill topbar-pill--button"
      onClick={onProviderClick}
      title={t('common.openSettingsForModel')}
    >
      {provider && model
        ? (
          <>
            {/* Model at rest; the provider prefix pays for its label
                only under the cursor (5a — icon at rest, label on
                hover, expanding leftward so the primary never moves) */}
            <span className="topbar-btn__label topbar-btn__label--lead">{provider} ·</span>
            <span className="topbar-pill-muted">{model}</span>
          </>
        )
        : (
          <>
            {provider && <span>{provider}</span>}
            {model && <span className="topbar-pill-muted">{model}</span>}
          </>
        )}
    </button>
  );
}
