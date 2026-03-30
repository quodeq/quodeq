const REF_TYPES = ['url', 'rfc', 'cwe', 'cve', 'owasp', 'nist', 'iso', 'other'];

function ReferenceRow({ refData, index, onChange, onRemove }) {
  const ref = refData;
  return (
    <div className="ref-row">
      <select
        className="ref-type-select"
        value={ref.type || 'url'}
        onChange={(e) => onChange(index, 'type', e.target.value)}
        aria-label="Reference type"
      >
        {REF_TYPES.map((t) => (
          <option key={t} value={t}>{t.toUpperCase()}</option>
        ))}
      </select>
      <input
        className="ref-label-input"
        placeholder="Label"
        value={ref.label || ''}
        onChange={(e) => onChange(index, 'label', e.target.value)}
        aria-label="Reference label"
      />
      <input
        className="ref-url-input"
        placeholder="URL or identifier"
        value={ref.url || ''}
        onChange={(e) => onChange(index, 'url', e.target.value)}
        aria-label="Reference URL"
      />
      <button
        type="button"
        className="ref-remove-btn"
        onClick={() => onRemove(index)}
        aria-label="Remove reference"
        title="Remove"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

export default function ReferenceEditor({ refs, onChange, disabled }) {
  const handleChange = (index, field, value) => {
    const updated = refs.map((r, i) => i === index ? { ...r, [field]: value } : r);
    onChange(updated);
  };

  const handleAdd = () => {
    onChange([...refs, { type: 'url', label: '', url: '' }]);
  };

  const handleRemove = (index) => {
    onChange(refs.filter((_, i) => i !== index));
  };

  return (
    <div className="reference-editor">
      <div className="reference-editor-header">
        <span className="reference-editor-label">References</span>
        {!disabled && (
          <button type="button" className="ref-add-btn" onClick={handleAdd}>
            + Add Reference
          </button>
        )}
      </div>
      {refs.length === 0 && (
        <p className="reference-editor-empty">No references yet.</p>
      )}
      {refs.map((ref, i) => (
        <ReferenceRow
          key={i}
          refData={ref}
          index={i}
          onChange={disabled ? () => {} : handleChange}
          onRemove={disabled ? () => {} : handleRemove}
        />
      ))}
    </div>
  );
}
