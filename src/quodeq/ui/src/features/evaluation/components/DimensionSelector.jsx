import { useMemo } from 'react';

const TYPE_CONFIG = {
  quodeq:    { label: 'Quodeq',    className: 'dimension-chip-type--quodeq',    order: 1 },
  custom:    { label: 'Custom',    className: 'dimension-chip-type--custom',    order: 3 },
  community: { label: 'Community', className: 'dimension-chip-type--community', order: 2 },
};
const DEFAULT_TYPE_CONFIG = { label: 'ISO', className: 'dimension-chip-type--builtin', order: 0 };

function typeInfo(dim) { return TYPE_CONFIG[dim.standardType] || DEFAULT_TYPE_CONFIG; }

function DimensionChip({ dim, isSelected, onToggle }) {
  const info = typeInfo(dim);
  return (
    <button
      type="button"
      className={`dimension-chip-btn${isSelected ? ' selected' : ''}`}
      title={dim.iso_25010 ? `ISO 25010: ${dim.iso_25010}` : dim.label || dim.id}
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
      title={dim.iso_25010 ? `ISO 25010: ${dim.iso_25010}` : dim.label || dim.id}
      aria-pressed={isSelected}
      onClick={() => onToggle(dim.id)}
    >
      <span className="eval-dim-card__check" aria-hidden="true">{isSelected ? '✓' : ''}</span>
      <span className="eval-dim-card__body">
        <span className="eval-dim-card__title-row">
          <span className="eval-dim-card__name">{dim.label || dim.id}</span>
          <span className={`eval-dim-card__std ${info.className}`}>{info.label.toLowerCase()}</span>
        </span>
        {meta != null ? (
          <span className="eval-dim-card__meta">{meta}</span>
        ) : metaLoading ? (
          // Estimates take a few seconds; a quiet placeholder keeps the card
          // from growing when the real meta lands.
          <span className="eval-dim-card__meta eval-dim-card__meta--skeleton" title="estimating…" aria-hidden="true" />
        ) : null}
      </span>
    </button>
  );
}

/**
 * @param {object} props
 * @param {object} [props.dimMetas] terminal variant only: dim id → pre-run
 *   meta label ("312 files to analyze · 85% analyzed"); null/missing → omitted.
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

  const isTerm = variant === 'terminal';

  if (isTerm) {
    return (
      <div className="form-group">
        <div className="dimension-label-row dimension-label-row--terminal">
          <span className="eval-dims-heading">
            <label>dimensions</label>
            <span className="eval-dims-counter">
              {selectedDims.size} of {sorted.length} selected · run in order
            </span>
          </span>
          <div className="dimension-chip-actions">
            <button type="button" className="dim-action-btn dim-action-btn--terminal" onClick={onSelectAll}>all</button>
            <button type="button" className="dim-action-btn dim-action-btn--terminal" onClick={onClearAll}>clear</button>
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

  return (
    <div className="form-group">
      <div className="dimension-label-row">
        <label>Dimensions</label>
        <div className="dimension-chip-actions">
          <button type="button" className="dim-action-btn" onClick={onSelectAll}>All</button>
          <button type="button" className="dim-action-btn" onClick={onClearAll}>Clear</button>
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
