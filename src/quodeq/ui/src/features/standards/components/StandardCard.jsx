import { useState } from 'react';

const TYPE_LABELS = { builtin: 'Built-in', community: 'Community', custom: 'Custom' };

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

export default function StandardCard({ standard, onEdit, onDelete, onDuplicate }) {
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);

  const principleCount = standard.principles?.length ?? 0;
  const requirementCount = (standard.principles || []).reduce(
    (sum, p) => sum + (p.requirements?.length ?? 0),
    0
  );
  const isDeletable = standard.type !== 'builtin';

  return (
    <>
      <div className={`standard-card standard-card--${standard.type}`} onClick={() => onEdit(standard.id)}>
        <div className="standard-card-header">
          <span className={`standard-type-badge standard-type-badge--${standard.type}`}>
            {TYPE_LABELS[standard.type] || standard.type}
          </span>
          {standard.managed && (
            <span className="standard-managed-badge" title="Managed standard — read-only">managed</span>
          )}
        </div>

        <h3 className="standard-card-name">{standard.name}</h3>
        {standard.id && (
          <p className="standard-card-id">{standard.id}</p>
        )}
        {standard.description && (
          <p className="standard-card-description">{standard.description}</p>
        )}

        <div className="standard-card-counts">
          <span>{principleCount} {principleCount === 1 ? 'principle' : 'principles'}</span>
          <span className="standard-card-counts-sep">·</span>
          <span>{requirementCount} {requirementCount === 1 ? 'requirement' : 'requirements'}</span>
        </div>

        <div className="standard-card-actions" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            className="card-action-btn"
            onClick={() => onEdit(standard.id)}
            title="View / Edit"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
            </svg>
            Edit
          </button>
          <button
            type="button"
            className="card-action-btn"
            onClick={() => setShowDuplicateModal(true)}
            title="Duplicate"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
            Duplicate
          </button>
          {isDeletable && (
            <button
              type="button"
              className="card-action-btn card-action-btn--danger"
              onClick={() => setShowDeleteModal(true)}
              title="Delete"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6M14 11v6" />
                <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
              </svg>
              Delete
            </button>
          )}
        </div>
      </div>

      {showDeleteModal && (
        <ConfirmDeleteModal
          standardName={standard.name}
          principleCount={principleCount}
          requirementCount={requirementCount}
          onConfirm={() => { setShowDeleteModal(false); onDelete(standard.id); }}
          onCancel={() => setShowDeleteModal(false)}
        />
      )}
      {showDuplicateModal && (
        <DuplicateModal
          standardId={standard.id}
          onConfirm={(newId) => { setShowDuplicateModal(false); onDuplicate(standard.id, newId); }}
          onCancel={() => setShowDuplicateModal(false)}
        />
      )}
    </>
  );
}
