import { useMemo } from 'react';

const TYPE_CONFIG = {
  quodeq:    { label: 'Quodeq',    className: 'dimension-chip-type--quodeq',    order: 1 },
  custom:    { label: 'Custom',    className: 'dimension-chip-type--custom',    order: 3 },
  community: { label: 'Community', className: 'dimension-chip-type--community', order: 2 },
};
const DEFAULT_TYPE_CONFIG = { label: 'ISO', className: 'dimension-chip-type--builtin', order: 0 };

function typeInfo(dim) { return TYPE_CONFIG[dim.standardType] || DEFAULT_TYPE_CONFIG; }

function DimensionChip({ dim, isSelected, onToggle, variant }) {
  const info = typeInfo(dim);
  const isTerm = variant === 'terminal';
  return (
    <button
      type="button"
      className={`dimension-chip-btn${isTerm ? ' dimension-chip-btn--terminal' : ''}${isSelected ? ' selected' : ''}`}
      title={dim.iso_25010 ? `ISO 25010: ${dim.iso_25010}` : dim.label || dim.id}
      aria-pressed={isSelected}
      onClick={() => onToggle(dim.id)}
    >
      {isTerm && (
        <span className="dimension-chip-mark" aria-hidden="true">
          {isSelected ? '[x]' : '[ ]'}
        </span>
      )}
      {dim.label || dim.id}
      <span className={`dimension-chip-type${isTerm ? ' dimension-chip-type--terminal' : ''} ${info.className}`}>{info.label}</span>
    </button>
  );
}

export default function DimensionSelector({ allDimensions, selectedDims, onToggle, onSelectAll, onClearAll, variant }) {
  const sorted = useMemo(() => [...allDimensions].sort((a, b) => {
    const oa = (TYPE_CONFIG[a.standardType] || DEFAULT_TYPE_CONFIG).order;
    const ob = (TYPE_CONFIG[b.standardType] || DEFAULT_TYPE_CONFIG).order;
    if (oa !== ob) return oa - ob;
    return (a.label || a.id).localeCompare(b.label || b.id);
  }), [allDimensions]);

  const isTerm = variant === 'terminal';
  const cls = (base) => `${base}${isTerm ? ` ${base}--terminal` : ''}`;

  return (
    <div className="form-group">
      <div className={cls('dimension-label-row')}>
        <label>Dimensions</label>
        <div className="dimension-chip-actions">
          <button type="button" className={cls('dim-action-btn')} onClick={onSelectAll}>All</button>
          <button type="button" className={cls('dim-action-btn')} onClick={onClearAll}>Clear</button>
        </div>
      </div>

      <div className={cls('dimension-grid')}>
        {sorted.map((dim) => (
          <DimensionChip key={dim.id} dim={dim} isSelected={selectedDims.has(dim.id)} onToggle={onToggle} variant={variant} />
        ))}
      </div>
    </div>
  );
}
