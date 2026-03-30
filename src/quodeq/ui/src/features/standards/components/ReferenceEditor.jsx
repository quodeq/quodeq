import { useState, useEffect, useRef } from 'react';
import { listCwes } from '../../../api/index.js';

const EDITABLE_REF_TYPES = ['cwe', 'book', 'url', 'other'];
const BUILTIN_REF_TYPES = ['cwe', 'asvs', 'cert', 'cisq', 'wcag22'];

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

const ABSTRACTION_ORDER = ['Base', 'Variant', 'Class', 'Compound', 'Pillar', 'Category'];

function CweBrowserModal({ onSelect, onClose }) {
  const [cwes, setCwes] = useState([]);
  const [query, setQuery] = useState('');
  const [filterAbstraction, setFilterAbstraction] = useState('');
  const searchRef = useRef(null);

  useEffect(() => {
    listCwes().then(setCwes).catch(() => setCwes([]));
  }, []);

  useEffect(() => {
    if (searchRef.current) searchRef.current.focus();
  }, []);

  const filtered = cwes.filter((c) => {
    if (filterAbstraction && c.abstraction !== filterAbstraction) return false;
    if (!query) return true;
    return String(c.id).includes(query) || c.name.toLowerCase().includes(query.toLowerCase());
  });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="cwe-browser-modal" onClick={(e) => e.stopPropagation()}>
        <div className="cwe-browser-header">
          <h3 className="cwe-browser-title">Select CWE</h3>
          <button type="button" className="modal-close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="cwe-browser-toolbar">
          <input
            ref={searchRef}
            className="cwe-browser-search"
            placeholder="Search by ID or name..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select
            className="cwe-browser-filter"
            value={filterAbstraction}
            onChange={(e) => setFilterAbstraction(e.target.value)}
          >
            <option value="">All types</option>
            {ABSTRACTION_ORDER.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </div>

        <div className="cwe-browser-count">{filtered.length} of {cwes.length} CWEs</div>

        <div className="cwe-browser-list">
          {filtered.map((c) => (
            <div
              key={c.id}
              className="cwe-browser-item"
              onClick={() => { onSelect(c); onClose(); }}
            >
              <div className="cwe-browser-item-header">
                <span className="cwe-browser-item-id">CWE-{c.id}</span>
                <span className="cwe-browser-item-abstraction">{c.abstraction}</span>
              </div>
              <div className="cwe-browser-item-name">{c.name}</div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="cwe-browser-empty">No CWEs match your search.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function CweSelector({ value, name, onSelect, disabled }) {
  const [showBrowser, setShowBrowser] = useState(false);

  return (
    <>
      <button
        type="button"
        className="cwe-select-btn"
        onClick={() => !disabled && setShowBrowser(true)}
        disabled={disabled}
      >
        {value ? `CWE-${value}` : 'Select CWE...'}
      </button>
      {name && <span className="ref-cwe-name" title={name}>{name}</span>}
      {showBrowser && (
        <CweBrowserModal
          onSelect={onSelect}
          onClose={() => setShowBrowser(false)}
        />
      )}
    </>
  );
}

const NAME_PLACEHOLDERS = {
  book: 'Title (e.g. Clean Architecture Ch.22)',
  url: 'Description',
  other: 'Description',
};

function ReferenceRow({ refData, index, onChange, onRemove, disabled }) {
  const ref = normalizeRef(refData);
  const isCwe = ref.type === 'cwe';

  // Build type options: editable types for custom, include current type for built-in
  const typeOptions = disabled
    ? [...new Set([ref.type, ...BUILTIN_REF_TYPES, ...EDITABLE_REF_TYPES])]
    : EDITABLE_REF_TYPES;

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

  const handleFieldChange = (field, value) => {
    onChange(index, { ...ref, [field]: value });
  };

  return (
    <div className="ref-row">
      <select
        className="ref-type-select"
        value={typeOptions.includes(ref.type) ? ref.type : 'other'}
        onChange={(e) => handleTypeChange(e.target.value)}
        disabled={disabled}
        aria-label="Reference type"
      >
        {typeOptions.map((t) => (
          <option key={t} value={t}>{t.toUpperCase()}</option>
        ))}
      </select>

      {isCwe ? (
        <CweSelector value={ref.refId} name={ref.name} onSelect={handleCweSelect} disabled={disabled} />
      ) : (
        <>
          {ref.refId && (
            <span className="ref-builtin-id">{ref.type.toUpperCase()}-{ref.refId}</span>
          )}
          <input
            className="ref-name-input"
            placeholder={NAME_PLACEHOLDERS[ref.type] || 'Description'}
            value={ref.name}
            onChange={(e) => handleFieldChange('name', e.target.value)}
            disabled={disabled}
            aria-label="Reference name"
          />
        </>
      )}

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
