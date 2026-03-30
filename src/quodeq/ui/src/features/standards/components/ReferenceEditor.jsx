import { useState, useEffect, useRef } from 'react';
import { listCwes } from '../../../api/index.js';

const REF_TYPES = ['cwe', 'owasp', 'nist', 'iso', 'rfc', 'book', 'url', 'other'];

const URL_TEMPLATES = {
  cwe: (id) => `https://cwe.mitre.org/data/definitions/${id}.html`,
};

/** Normalize built-in format {source, id, name, url} to editor format */
function normalizeRef(ref) {
  if (ref.source && !ref.type) {
    return { type: ref.source, refId: String(ref.id || ''), name: ref.name || '', url: ref.url || '' };
  }
  return { type: ref.type || 'url', refId: ref.refId || ref.id || '', name: ref.name || ref.label || '', url: ref.url || '' };
}

function formatRefDisplay(ref) {
  const n = normalizeRef(ref);
  const prefix = n.type ? n.type.toUpperCase() : '';
  const id = n.refId ? `${prefix}-${n.refId}` : prefix;
  return n.name ? `${id}: ${n.name}` : id;
}

function CweSearch({ value, onSelect, disabled }) {
  const [cwes, setCwes] = useState([]);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    listCwes().then(setCwes).catch(() => setCwes([]));
  }, []);

  useEffect(() => {
    function handleClickOutside(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const filtered = query
    ? cwes.filter((c) => String(c.id).includes(query) || c.name.toLowerCase().includes(query.toLowerCase())).slice(0, 20)
    : cwes.slice(0, 20);

  return (
    <div className="cwe-search" ref={wrapperRef}>
      <input
        className="ref-id-input"
        placeholder="Search CWE..."
        value={open ? query : (value ? `CWE-${value}` : '')}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        disabled={disabled}
        aria-label="Search CWE"
      />
      {open && filtered.length > 0 && (
        <div className="cwe-search-dropdown">
          {filtered.map((c) => (
            <div
              key={c.id}
              className={`cwe-search-option${String(c.id) === String(value) ? ' cwe-search-option--selected' : ''}`}
              onClick={() => { onSelect(c); setQuery(''); setOpen(false); }}
            >
              <span className="cwe-search-id">CWE-{c.id}</span>
              <span className="cwe-search-name">{c.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ReferenceRow({ refData, index, onChange, onRemove, disabled }) {
  const ref = normalizeRef(refData);
  const isCwe = ref.type === 'cwe';
  const showFreeId = !isCwe && ['owasp', 'nist', 'iso', 'rfc'].includes(ref.type);

  const handleTypeChange = (newType) => {
    onChange(index, { ...ref, type: newType, refId: '', name: '', url: '' });
  };

  const handleCweSelect = (cwe) => {
    onChange(index, {
      type: 'cwe',
      refId: String(cwe.id),
      name: cwe.name,
      url: URL_TEMPLATES.cwe(cwe.id),
    });
  };

  const handleIdChange = (newId) => {
    onChange(index, { ...ref, refId: newId });
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

      {isCwe && (
        <CweSearch value={ref.refId} onSelect={handleCweSelect} disabled={disabled} />
      )}

      {showFreeId && (
        <input
          className="ref-id-input"
          placeholder="ID"
          value={ref.refId}
          onChange={(e) => handleIdChange(e.target.value)}
          disabled={disabled}
          aria-label="Reference ID"
        />
      )}

      {!isCwe && (
        <input
          className="ref-name-input"
          placeholder={ref.type === 'book' ? 'Title (e.g. Clean Architecture Ch.22)' : ref.type === 'url' ? 'Description' : 'Name'}
          value={ref.name}
          onChange={(e) => handleFieldChange('name', e.target.value)}
          disabled={disabled}
          aria-label="Reference name"
        />
      )}

      {isCwe && ref.name && (
        <span className="ref-cwe-name" title={ref.name}>{ref.name}</span>
      )}

      <input
        className="ref-url-input"
        placeholder="URL"
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
