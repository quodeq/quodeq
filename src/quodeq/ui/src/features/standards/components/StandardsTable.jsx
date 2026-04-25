import { useMemo, useState } from 'react';
import { exportStandard } from '../../../api/index.js';
import { STANDARD_TYPES } from '../hooks/useStandards.js';
import { ICON_STAR_FILLED, ICON_STAR_OUTLINE } from '../../../constants/navigation.jsx';

const BASE_LABELS = {
  [STANDARD_TYPES.BUILTIN]: 'iso-25010',
  [STANDARD_TYPES.QUODEQ]: 'quodeq',
  [STANDARD_TYPES.COMMUNITY]: 'community',
  [STANDARD_TYPES.CUSTOM]: 'custom',
};

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
            <p className="modal-body">Type <strong>{standardName}</strong> to confirm:</p>
            <input className="modal-input" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={standardName} autoFocus />
          </>
        ) : (
          <p className="modal-body">Are you sure you want to delete <strong>{standardName}</strong>?</p>
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
        <input className="modal-input" value={newId} onChange={(e) => setNewId(e.target.value)} autoFocus />
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button type="button" className="btn-primary" onClick={() => onConfirm(newId)} disabled={!newId.trim()}>Duplicate</button>
        </div>
      </div>
    </div>
  );
}

async function downloadStandard(standardId) {
  const { data, fileName } = await exportStandard(standardId);
  const content = JSON.stringify(data, null, 2);
  if (window.pywebview?.api?.save_file) {
    window.pywebview.api.save_file(content, fileName);
    return;
  }
  const blob = new Blob([content], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function StarToggle({ isVisible, standardId, onToggleVisibility }) {
  return (
    <button
      type="button"
      className={`standards-star-btn${isVisible ? ' standards-star-btn--on' : ''}`}
      title={isVisible ? 'Enabled — click to disable' : 'Disabled — click to enable'}
      onClick={(e) => { e.stopPropagation(); onToggleVisibility(standardId); }}
    >
      {isVisible ? ICON_STAR_FILLED : ICON_STAR_OUTLINE}
    </button>
  );
}

function RowActions({ standard, isDeletable, isEditable, onOpen, onDuplicate, onDownload, onDelete }) {
  const openLabel = isEditable ? 'Edit' : 'View';
  return (
    <div className="standards-row-actions" onClick={(e) => e.stopPropagation()}>
      <button type="button" className="standards-row-action" onClick={onOpen} title={openLabel} aria-label={`${openLabel} ${standard.name}`}>
        {isEditable ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        )}
      </button>
      <button type="button" className="standards-row-action" onClick={onDuplicate} title="Duplicate" aria-label={`Duplicate ${standard.name}`}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      </button>
      <button type="button" className="standards-row-action" onClick={onDownload} title="Download" aria-label={`Download ${standard.name}`}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
      </button>
      {isDeletable && (
        <button type="button" className="standards-row-action standards-row-action--danger" onClick={onDelete} title="Delete" aria-label={`Delete ${standard.name}`}>
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

function isDeletableStandard(type) {
  return type !== STANDARD_TYPES.BUILTIN && type !== STANDARD_TYPES.QUODEQ;
}

function StandardRow({ standard, isVisible, onEdit, onDelete, onDuplicate, onToggleVisibility }) {
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  const principleCount = standard.principleCount ?? standard.principles?.length ?? 0;
  const requirementCount = standard.requirementCount ?? (standard.principles || []).reduce((sum, p) => sum + (p.requirements?.length ?? 0), 0);
  const isDeletable = isDeletableStandard(standard.type);
  const baseLabel = BASE_LABELS[standard.type] || standard.type;

  return (
    <>
      <div
        className={`standards-row${isVisible ? '' : ' standards-row--disabled'}`}
        role="button"
        tabIndex={0}
        aria-pressed={isVisible}
        onClick={() => onToggleVisibility(standard.id)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggleVisibility(standard.id); } }}
      >
        <div className="standards-cell standards-cell--name">
          <span className="standards-row-name">{standard.name}</span>
          {standard.description && <span className="standards-row-subtitle">{standard.description}</span>}
        </div>
        <div className="standards-cell standards-cell--base">
          <span className={`standards-base-pill standards-base-pill--${standard.type}`}>{baseLabel}</span>
        </div>
        <div className="standards-cell standards-cell--num">{principleCount}</div>
        <div className="standards-cell standards-cell--num">{requirementCount}</div>
        <div className="standards-cell standards-cell--enabled">
          <StarToggle isVisible={isVisible} standardId={standard.id} onToggleVisibility={onToggleVisibility} />
        </div>
        <div className="standards-cell standards-cell--actions">
          <RowActions
            standard={standard}
            isDeletable={isDeletable}
            isEditable={isDeletable}
            onOpen={() => onEdit(standard.id)}
            onDuplicate={() => setShowDuplicateModal(true)}
            onDownload={() => downloadStandard(standard.id)}
            onDelete={() => setShowDeleteModal(true)}
          />
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

export default function StandardsTable({ grouped, actions }) {
  const { onEdit, onDelete, onDuplicate, isVisible, onToggleVisibility } = actions;
  const all = useMemo(
    () => [...(grouped.builtin || []), ...(grouped.quodeq || []), ...(grouped.community || []), ...(grouped.custom || [])],
    [grouped],
  );

  if (all.length === 0) {
    return (
      <div className="standards-empty">
        <p>No standards found. Import from the library or create a custom standard.</p>
      </div>
    );
  }

  return (
    <div className="standards-table" role="table">
      <div className="standards-table-head" role="row">
        <div className="standards-cell standards-cell--name">Name</div>
        <div className="standards-cell standards-cell--base">Base</div>
        <div className="standards-cell standards-cell--num">Principles</div>
        <div className="standards-cell standards-cell--num">Requirements</div>
        <div className="standards-cell standards-cell--enabled">Enabled</div>
        <div className="standards-cell standards-cell--actions" />
      </div>
      <div className="standards-table-body">
        {all.map((s) => (
          <StandardRow
            key={s.id}
            standard={s}
            isVisible={isVisible(s.id)}
            onEdit={onEdit}
            onDelete={onDelete}
            onDuplicate={onDuplicate}
            onToggleVisibility={onToggleVisibility}
          />
        ))}
      </div>
    </div>
  );
}
