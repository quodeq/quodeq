const REF_TYPES = ['cwe', 'cve', 'owasp', 'nist', 'iso', 'rfc', 'book', 'url', 'other'];

const URL_TEMPLATES = {
  cwe: (id) => `https://cwe.mitre.org/data/definitions/${id}.html`,
  cve: (id) => `https://www.cve.org/CVERecord?id=CVE-${id}`,
};

/** Normalize built-in format {source, id, name, url} to editor format {type, refId, name, url} */
function normalizeRef(ref) {
  if (ref.source && !ref.type) {
    return {
      type: ref.source,
      refId: ref.id || '',
      name: ref.name || '',
      url: ref.url || '',
    };
  }
  return {
    type: ref.type || 'url',
    refId: ref.refId || ref.id || '',
    name: ref.name || ref.label || '',
    url: ref.url || '',
  };
}

function ReferenceRow({ refData, index, onChange, onRemove, disabled }) {
  const ref = normalizeRef(refData);
  const showId = ['cwe', 'cve', 'owasp', 'nist', 'iso', 'rfc'].includes(ref.type);

  const handleTypeChange = (newType) => {
    const updated = { ...ref, type: newType };
    if (URL_TEMPLATES[newType] && ref.refId) {
      updated.url = URL_TEMPLATES[newType](ref.refId);
    }
    onChange(index, updated);
  };

  const handleIdChange = (newId) => {
    const updated = { ...ref, refId: newId };
    if (URL_TEMPLATES[ref.type] && newId) {
      updated.url = URL_TEMPLATES[ref.type](newId);
    }
    onChange(index, updated);
  };

  const handleFieldChange = (field, value) => {
    onChange(index, { ...ref, [field]: value });
  };

  return (
    <div className="ref-row">
      <select
        className="ref-type-select"
        value={ref.type}
        onChange={(e) => handleTypeChange(e.target.value)}
        disabled={disabled}
        aria-label="Reference type"
      >
        {REF_TYPES.map((t) => (
          <option key={t} value={t}>{t.toUpperCase()}</option>
        ))}
      </select>
      {showId && (
        <input
          className="ref-id-input"
          placeholder="ID (e.g. 209)"
          value={ref.refId}
          onChange={(e) => handleIdChange(e.target.value)}
          disabled={disabled}
          aria-label="Reference ID"
        />
      )}
      <input
        className="ref-name-input"
        placeholder={showId ? 'Name (e.g. Hardcoded Credentials)' : 'Description'}
        value={ref.name}
        onChange={(e) => handleFieldChange('name', e.target.value)}
        disabled={disabled}
        aria-label="Reference name"
      />
      <input
        className="ref-url-input"
        placeholder="URL (optional)"
        value={ref.url}
        onChange={(e) => handleFieldChange('url', e.target.value)}
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
  const handleChange = (index, updatedRef) => {
    const updated = refs.map((r, i) => i === index ? updatedRef : r);
    onChange(updated);
  };

  const handleAdd = () => {
    onChange([...refs, { type: 'cwe', refId: '', name: '', url: '' }]);
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
