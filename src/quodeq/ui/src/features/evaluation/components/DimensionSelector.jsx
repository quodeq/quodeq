const TYPE_CONFIG = {
  quodeq:    { label: 'Quodeq',    className: 'dimension-chip-type--quodeq' },
  custom:    { label: 'Custom',    className: 'dimension-chip-type--custom' },
  community: { label: 'Community', className: 'dimension-chip-type--community' },
};
const DEFAULT_TYPE_CONFIG = { label: 'ISO', className: 'dimension-chip-type--builtin' };

function typeInfo(dim) { return TYPE_CONFIG[dim.standardType] || DEFAULT_TYPE_CONFIG; }

function DimensionChip({ dim, isSelected, onToggle }) {
  const info = typeInfo(dim);
  return (
    <button
      type="button"
      className={`dimension-chip-btn ${isSelected ? 'selected' : ''}`}
      title={dim.iso_25010 ? `ISO 25010: ${dim.iso_25010}` : dim.label || dim.id}
      aria-pressed={isSelected}
      onClick={() => onToggle(dim.id)}
    >
      {dim.label || dim.id}
      <span className={`dimension-chip-type ${info.className}`}>{info.label}</span>
    </button>
  );
}

export default function DimensionSelector({ allDimensions, selectedDims, onToggle, onSelectAll, onClearAll }) {
  const sorted = [...allDimensions].sort((a, b) => (a.label || a.id).localeCompare(b.label || b.id));

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
