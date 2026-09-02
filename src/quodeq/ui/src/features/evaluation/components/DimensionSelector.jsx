import { useMemo } from 'react';
import { t } from '../../../strings/index.js';

const TYPE_CONFIG = {
  quodeq:    { label: t('evaluate.stdQuodeq'),    className: 'dimension-chip-type--quodeq',    order: 1 },
  custom:    { label: t('evaluate.stdCustom'),    className: 'dimension-chip-type--custom',    order: 3 },
  community: { label: t('evaluate.stdCommunity'), className: 'dimension-chip-type--community', order: 2 },
};
const DEFAULT_TYPE_CONFIG = { label: t('evaluate.stdIso'), className: 'dimension-chip-type--builtin', order: 0 };

function typeInfo(dim) { return TYPE_CONFIG[dim.standardType] || DEFAULT_TYPE_CONFIG; }

function DimensionChip({ dim, isSelected, onToggle }) {
  const info = typeInfo(dim);
  return (
    <button
      type="button"
      className={`dimension-chip-btn${isSelected ? ' selected' : ''}`}
      title={dim.iso_25010 ? t('evaluate.iso25010Title', { value: dim.iso_25010 }) : dim.label || dim.id}
      aria-pressed={isSelected}
      onClick={() => onToggle(dim.id)}
    >
      {dim.label || dim.id}
      <span className={`dimension-chip-type ${info.className}`}>{info.label}</span>
    </button>
  );
}

function DimensionCard({ dim, isSelected, onToggle, meta, metaLoading }) {
  const info = typeInfo(dim);
  return (
    <button
      type="button"
      className={`eval-dim-card${isSelected ? ' eval-dim-card--selected' : ''}`}
      title={dim.iso_25010 ? t('evaluate.iso25010Title', { value: dim.iso_25010 }) : dim.label || dim.id}
      aria-pressed={isSelected}
      onClick={() => onToggle(dim.id)}
    >
      <span className="eval-dim-card__check" aria-hidden="true">{isSelected ? '✓' : ''}</span>
      <span className="eval-dim-card__body">
        <span className="eval-dim-card__title-row">
          <span className="eval-dim-card__name">{dim.label || dim.id}</span>
          {/* Plain bordered tag on purpose: the legacy dimension-chip-type--*
              classes paint a tinted pill that fights the card style and
              drops contrast on several themes. */}
          <span className="eval-dim-card__std">{info.label.toLowerCase()}</span>
        </span>
        {meta != null ? (
          <span className="eval-dim-card__meta">
            {meta.map((line) => (
              <span key={line} className="eval-dim-card__meta-line">{line}</span>
            ))}
          </span>
        ) : metaLoading ? (
          // Estimates take a few seconds; a quiet placeholder keeps the card
          // from growing when the real meta lands.
          <span className="eval-dim-card__meta eval-dim-card__meta--skeleton" title={t('evaluate.estimating')} aria-hidden="true" />
        ) : null}
      </span>
    </button>
  );
}

function DimensionSelectorTerminal({ sorted, selectedDims, onToggle, onSelectAll, onClearAll, dimMetas, metasLoading }) {
  return (
    <div className="form-group eval-dims-section">
      <div className="dimension-label-row dimension-label-row--terminal">
        <span className="eval-dims-heading">
          <label>{t('evaluate.dimensionsLabel')}</label>
          <span className="eval-dims-counter">
            {t('evaluate.dimsSelectedCounter', { selected: selectedDims.size, total: sorted.length })}
          </span>
        </span>
        <div className="dimension-chip-actions">
          <button type="button" className="dim-action-btn dim-action-btn--terminal" onClick={onSelectAll}>{t('evaluate.allBtn')}</button>
          <button type="button" className="dim-action-btn dim-action-btn--terminal" onClick={onClearAll}>{t('evaluate.clearBtn')}</button>
        </div>
      </div>

      <div className="eval-dim-grid">
        {sorted.map((dim) => (
          <DimensionCard
            key={dim.id}
            dim={dim}
            isSelected={selectedDims.has(dim.id)}
            onToggle={onToggle}
            meta={dimMetas?.[dim.id] ?? null}
            metaLoading={metasLoading}
          />
        ))}
      </div>
    </div>
  );
}

function DimensionSelectorChips({ sorted, selectedDims, onToggle, onSelectAll, onClearAll }) {
  return (
    <div className="form-group">
      <div className="dimension-label-row">
        <label>{t('evaluate.dimensionsLabelCap')}</label>
        <div className="dimension-chip-actions">
          <button type="button" className="dim-action-btn" onClick={onSelectAll}>{t('evaluate.allCap')}</button>
          <button type="button" className="dim-action-btn" onClick={onClearAll}>{t('evaluate.clearCap')}</button>
        </div>
      </div>

      <div className="dimension-grid">
        {sorted.map((dim) => (
          <DimensionChip key={dim.id} dim={dim} isSelected={selectedDims.has(dim.id)} onToggle={onToggle} />
        ))}
      </div>
    </div>
  );
}

/**
 * @param {object} props
 * @param {object} [props.dimMetas] terminal variant only: dim id → pre-run
 *   meta lines (["312 files to analyze", "85% analyzed"]); null/missing → omitted.
 * @param {boolean} [props.metasLoading] terminal variant only: estimates are
 *   still being computed — cards show a small placeholder instead of nothing.
 */
export default function DimensionSelector({ allDimensions, selectedDims, onToggle, onSelectAll, onClearAll, variant, dimMetas = null, metasLoading = false }) {
  const sorted = useMemo(() => [...allDimensions].sort((a, b) => {
    const oa = (TYPE_CONFIG[a.standardType] || DEFAULT_TYPE_CONFIG).order;
    const ob = (TYPE_CONFIG[b.standardType] || DEFAULT_TYPE_CONFIG).order;
    if (oa !== ob) return oa - ob;
    return (a.label || a.id).localeCompare(b.label || b.id);
  }), [allDimensions]);

  const shared = { sorted, selectedDims, onToggle, onSelectAll, onClearAll };

  return variant === 'terminal'
    ? <DimensionSelectorTerminal {...shared} dimMetas={dimMetas} metasLoading={metasLoading} />
    : <DimensionSelectorChips {...shared} />;
}
