function typeLabel(dim) {
  if (dim.standardType === 'quodeq') return 'Quodeq';
  if (dim.standardType === 'custom') return 'Custom';
  if (dim.standardType === 'community') return 'Community';
  return 'ISO';
}

function typeClass(dim) {
  if (dim.standardType === 'quodeq') return 'dimension-chip-type--quodeq';
  if (dim.standardType === 'custom') return 'dimension-chip-type--custom';
  if (dim.standardType === 'community') return 'dimension-chip-type--community';
  return 'dimension-chip-type--builtin';
}

function DimensionChip({ dim, isSelected, onToggle }) {
  return (
    <button
      type="button"
      className={`dimension-chip-btn ${isSelected ? 'selected' : ''}`}
      title={dim.iso_25010 ? `ISO 25010: ${dim.iso_25010}` : dim.label || dim.id}
      aria-pressed={isSelected}
      onClick={() => onToggle(dim.id)}
    >
      {dim.label || dim.id}
      <span className={`dimension-chip-type ${typeClass(dim)}`}>{typeLabel(dim)}</span>
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
