const REF_TYPES = ['cwe', 'cve', 'owasp', 'nist', 'iso', 'rfc', 'book', 'url', 'other'];

/** Normalize built-in format {source, id, name, url} to editor format {type, label, url} */
function normalizeRef(ref) {
  if (ref.source && !ref.type) {
    const id = ref.id ? `${ref.source.toUpperCase()}-${ref.id}` : '';
    const label = ref.name ? `${id}: ${ref.name}`.trim() : id;
    return { type: ref.source, label: label || '', url: ref.url || '' };
  }
  return { type: ref.type || 'url', label: ref.label || ref.name || '', url: ref.url || '' };
}

function ReferenceRow({ refData, index, onChange, onRemove, disabled }) {
  const ref = normalizeRef(refData);
  return (
    <div className="ref-row">
      <select
        className="ref-type-select"
        value={ref.type}
        onChange={(e) => onChange(index, 'type', e.target.value)}
        disabled={disabled}
        aria-label="Reference type"
      >
        {REF_TYPES.map((t) => (
          <option key={t} value={t}>{t.toUpperCase()}</option>
        ))}
      </select>
      <input
        className="ref-label-input"
        placeholder="Label (e.g. CWE-798: Hardcoded Credentials)"
        value={ref.label}
        onChange={(e) => onChange(index, 'label', e.target.value)}
        disabled={disabled}
        aria-label="Reference label"
      />
      <input
        className="ref-url-input"
        placeholder="URL (optional)"
        value={ref.url}
        onChange={(e) => onChange(index, 'url', e.target.value)}
        disabled={disabled}
        aria-label="Reference URL"
      />
      {!disabled && (
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
      )}
    </div>
  );
}

export default function ReferenceEditor({ refs, onChange, disabled }) {
  const handleChange = (index, field, value) => {
    const updated = refs.map((r, i) => i === index ? { ...normalizeRef(r), [field]: value } : r);
    onChange(updated);
  };

  const handleAdd = () => {
    onChange([...refs, { type: 'cwe', label: '', url: '' }]);
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
          onChange={handleChange}
          onRemove={handleRemove}
          disabled={disabled}
        />
      ))}
    </div>
  );
}
