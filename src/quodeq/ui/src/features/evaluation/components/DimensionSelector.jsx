import { ISO_25010_URL } from '../../../constants.js';

function DimensionChip({ dim, isSelected, onToggle }) {
  return (
    <button
      type="button"
      className={`dimension-chip-btn ${isSelected ? 'selected' : ''}${dim.standardType ? ` dimension-chip-btn--${dim.standardType}` : ''}`}
      title={dim.iso_25010 ? `ISO 25010: ${dim.iso_25010}` : dim.label || dim.id}
      aria-pressed={isSelected}
      onClick={() => onToggle(dim.id)}
    >
      {dim.label || dim.id}
    </button>
  );
}

export default function DimensionSelector({ allDimensions, selectedDims, onToggle, onSelectAll, onClearAll }) {
  const builtin = [...allDimensions].filter((d) => !d.standardType).sort((a, b) => a.id.localeCompare(b.id));
  const custom = [...allDimensions].filter((d) => d.standardType).sort((a, b) => (a.label || a.id).localeCompare(b.label || b.id));

  return (
    <div className="form-group">
      <div className="dimension-label-row">
        <label>Dimensions</label>
        <div className="dimension-chip-actions">
          <button type="button" className="dim-action-btn" onClick={onSelectAll}>All</button>
          <button type="button" className="dim-action-btn" onClick={onClearAll}>Clear</button>
        </div>
      </div>

      {builtin.length > 0 && (
        <div className="dimension-section">
          <div className="dimension-section-label">
            <a className="iso-link" href={ISO_25010_URL} target="_blank" rel="noopener noreferrer">ISO 25010</a>
          </div>
          <div className="dimension-grid">
            {builtin.map((dim) => (
              <DimensionChip key={dim.id} dim={dim} isSelected={selectedDims.has(dim.id)} onToggle={onToggle} />
            ))}
          </div>
        </div>
      )}

      {custom.length > 0 && (
        <div className="dimension-section">
          <div className="dimension-section-label">Custom Standards</div>
          <div className="dimension-grid">
            {custom.map((dim) => (
              <DimensionChip key={dim.id} dim={dim} isSelected={selectedDims.has(dim.id)} onToggle={onToggle} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
