import { useState } from 'react';
import { exportStandard } from '../../../api/index.js';
import { STANDARD_TYPES } from '../hooks/useStandards.js';

const TYPE_LABELS = { [STANDARD_TYPES.BUILTIN]: 'ISO-25010', [STANDARD_TYPES.QUODEQ]: 'Quodeq', [STANDARD_TYPES.COMMUNITY]: 'Community', [STANDARD_TYPES.CUSTOM]: 'Custom' };

function ConfirmDeleteModal({ standardName, principleCount, requirementCount, onConfirm, onCancel }) {
  const [typed, setTyped] = useState('');
  const hasContent = principleCount > 0 || requirementCount > 0;
  const confirmText = standardName.toLowerCase().trim();
  const canDelete = !hasContent || typed.toLowerCase().trim() === confirmText;

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-title">Delete Standard</h3>
        {hasContent ? (
          <>
            <p className="modal-body modal-body--warning">
              <strong>{standardName}</strong> contains <strong>{principleCount} principle{principleCount !== 1 ? 's' : ''}</strong> and <strong>{requirementCount} requirement{requirementCount !== 1 ? 's' : ''}</strong>. This action cannot be undone.
            </p>
            <p className="modal-body">
              Type <strong>{standardName}</strong> to confirm:
            </p>
            <input
              className="modal-input"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={standardName}
              autoFocus
            />
          </>
        ) : (
          <p className="modal-body">
            Are you sure you want to delete <strong>{standardName}</strong>?
          </p>
        )}
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button type="button" className="btn-danger" onClick={onConfirm} disabled={!canDelete}>Delete</button>
        </div>
      </div>
    </div>
  );
}

function DuplicateModal({ standardId, onConfirm, onCancel }) {
  const [newId, setNewId] = useState(`${standardId}-copy`);
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-title">Duplicate Standard</h3>
        <p className="modal-body">Enter an ID for the new standard:</p>
        <input
          className="modal-input"
          value={newId}
          onChange={(e) => setNewId(e.target.value)}
          autoFocus
        />
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button type="button" className="btn-primary" onClick={() => onConfirm(newId)} disabled={!newId.trim()}>
            Duplicate
          </button>
        </div>
      </div>
    </div>
  );
}

function CardActions({ standard, isDeletable, onDuplicate, onDownload, onDelete }) {
  return (
    <div className="standard-card-actions" onClick={(e) => e.stopPropagation()}>
      <button type="button" className="card-action-btn" onClick={onDuplicate} title="Duplicate">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      </button>
      <button type="button" className="card-action-btn" onClick={onDownload} title="Download">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
      </button>
      {isDeletable && (
        <button type="button" className="card-action-btn card-action-btn--danger" onClick={onDelete} title="Delete">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6M14 11v6" />
            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          </svg>
        </button>
      )}
    </div>
  );
}

function EyeToggle({ isVisible, standardId, onToggleVisibility }) {
  return (
    <button
      type="button"
      className={`eye-toggle-btn${isVisible ? ' eye-toggle-btn--on' : ''}`}
      title={isVisible ? 'Visible on Overview — click to hide' : 'Hidden from Overview — click to show'}
      onClick={(e) => { e.stopPropagation(); onToggleVisibility(standardId); }}
    >
      {isVisible ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
          <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
          <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
          <line x1="1" y1="1" x2="23" y2="23" />
        </svg>
      )}
    </button>
  );
}

async function downloadStandard(standardId) {
  const { data, fileName } = await exportStandard(standardId);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function StandardCardBody({ standard, isVisible, onToggleVisibility, principleCount, requirementCount }) {
  return (
    <>
      <div className="standard-card-header">
        <span className={`standard-type-badge standard-type-badge--${standard.type}`}>
          {TYPE_LABELS[standard.type] || standard.type}
        </span>
        {standard.managed && (
          <span className="standard-managed-badge" title="Managed standard — read-only">managed</span>
        )}
        <EyeToggle isVisible={isVisible} standardId={standard.id} onToggleVisibility={onToggleVisibility} />
      </div>
      <h3 className="standard-card-name">{standard.name}</h3>
      {standard.description && <p className="standard-card-description">{standard.description}</p>}
      <div className="standard-card-counts">
        <span>{principleCount} {principleCount === 1 ? 'principle' : 'principles'}</span>
        <span className="standard-card-counts-sep">·</span>
        <span>{requirementCount} {requirementCount === 1 ? 'requirement' : 'requirements'}</span>
      </div>
    </>
  );
}

export default function StandardCard({ standard, onEdit, onDelete, onDuplicate, isVisible, onToggleVisibility }) {
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  const principleCount = standard.principleCount ?? standard.principles?.length ?? 0;
  const requirementCount = standard.requirementCount ?? (standard.principles || []).reduce((sum, p) => sum + (p.requirements?.length ?? 0), 0);
  const isDeletable = standard.type !== STANDARD_TYPES.BUILTIN && standard.type !== STANDARD_TYPES.QUODEQ;
  const visClass = isVisible ? 'standard-card--visible' : 'standard-card--hidden';

  return (
    <>
      <div className={`standard-card ${visClass}`} onClick={() => onEdit(standard.id)}>
        <StandardCardBody standard={standard} isVisible={isVisible} onToggleVisibility={onToggleVisibility} principleCount={principleCount} requirementCount={requirementCount} />
        <CardActions isDeletable={isDeletable} onDuplicate={() => setShowDuplicateModal(true)} onDownload={() => downloadStandard(standard.id)} onDelete={() => setShowDeleteModal(true)} />
      </div>
      {showDeleteModal && <ConfirmDeleteModal standardName={standard.name} principleCount={principleCount} requirementCount={requirementCount} onConfirm={() => { setShowDeleteModal(false); onDelete(standard.id); }} onCancel={() => setShowDeleteModal(false)} />}
      {showDuplicateModal && <DuplicateModal standardId={standard.id} onConfirm={(newId) => { setShowDuplicateModal(false); onDuplicate(standard.id, newId); }} onCancel={() => setShowDuplicateModal(false)} />}
    </>
  );
}
