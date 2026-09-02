import { useMemo, useState } from 'react';
import { STANDARD_TYPES } from '../hooks/useStandards.js';
import { useStandardRowModals } from '../hooks/useStandardRowModals.js';
import { ICON_STAR_FILLED, ICON_STAR_OUTLINE } from '../../../constants/navigation.jsx';
import { t } from '../../../strings/index.js';

const BASE_LABELS = {
  [STANDARD_TYPES.BUILTIN]: t('standards.baseIso'),
  [STANDARD_TYPES.QUODEQ]: t('standards.baseQuodeq'),
  [STANDARD_TYPES.COMMUNITY]: t('standards.baseCommunity'),
  [STANDARD_TYPES.CUSTOM]: t('standards.baseCustom'),
};

function ConfirmDeleteModal({ standardName, principleCount, requirementCount, onConfirm, onCancel }) {
  const [typed, setTyped] = useState('');
  const hasContent = principleCount > 0 || requirementCount > 0;
  const confirmText = standardName.toLowerCase().trim();
  const canDelete = !hasContent || typed.toLowerCase().trim() === confirmText;

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-title">{t('standards.deleteStandardTitle')}</h3>
        {hasContent ? (
          <>
            <p className="modal-body modal-body--warning">
              <strong>{standardName}</strong> {t('standards.contains')} <strong>{principleCount === 1 ? t('standards.principlesCountOne', { count: principleCount }) : t('standards.principlesCountMany', { count: principleCount })}</strong> {t('standards.and')} <strong>{requirementCount === 1 ? t('standards.requirementsCountOne', { count: requirementCount }) : t('standards.requirementsCountMany', { count: requirementCount })}</strong>. {t('standards.cannotBeUndone')}
            </p>
            <p className="modal-body">{t('standards.typePrefix')} <strong>{standardName}</strong> {t('standards.toConfirmSuffix')}</p>
            <input className="modal-input" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={standardName} autoFocus />
          </>
        ) : (
          <p className="modal-body">{t('standards.deleteConfirmPrefix')} <strong>{standardName}</strong>?</p>
        )}
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>{t('common.cancel')}</button>
          <button type="button" className="btn-danger" onClick={onConfirm} disabled={!canDelete}>{t('violations.delete')}</button>
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
        <h3 className="modal-title">{t('standards.duplicateStandardTitle')}</h3>
        <p className="modal-body">{t('standards.enterNewId')}</p>
        <input className="modal-input" value={newId} onChange={(e) => setNewId(e.target.value)} autoFocus />
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>{t('common.cancel')}</button>
          <button type="button" className="btn-primary" onClick={() => onConfirm(newId)} disabled={!newId.trim()}>{t('standards.duplicate')}</button>
        </div>
      </div>
    </div>
  );
}

function StarToggle({ isVisible, standardId, onToggleVisibility }) {
  return (
    <button
      type="button"
      className={`standards-star-btn${isVisible ? ' standards-star-btn--on' : ''}`}
      title={isVisible ? t('standards.enabledTitle') : t('standards.disabledTitle')}
      onClick={(e) => { e.stopPropagation(); onToggleVisibility(standardId); }}
    >
      {isVisible ? ICON_STAR_FILLED : ICON_STAR_OUTLINE}
    </button>
  );
}

function RowActions({ standard, isDeletable, isEditable, onOpen, onDuplicate, onDownload, onDelete }) {
  const openLabel = isEditable ? t('standards.edit') : t('standards.view');
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
      <button type="button" className="standards-row-action" onClick={onDuplicate} title={t('standards.duplicate')} aria-label={`${t('standards.duplicate')} ${standard.name}`}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      </button>
      <button type="button" className="standards-row-action" onClick={onDownload} title={t('standards.download')} aria-label={`${t('standards.download')} ${standard.name}`}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
      </button>
      {isDeletable && (
        <button type="button" className="standards-row-action standards-row-action--danger" onClick={onDelete} title={t('violations.delete')} aria-label={`${t('violations.delete')} ${standard.name}`}>
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

function StandardRowMain({
  standard, isVisible, onToggleVisibility, baseLabel, customizedCounts, principleCount, requirementCount,
  isDeletable, onEdit, openDuplicate, handleDownload, openDelete,
}) {
  return (
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
        {customizedCounts?.[standard.id] > 0 && (
          <span className="standards-customized-badge">
            {t('standards.customizedCount', { count: customizedCounts[standard.id] })}
          </span>
        )}
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
          onDuplicate={openDuplicate}
          onDownload={handleDownload}
          onDelete={openDelete}
        />
      </div>
    </div>
  );
}

function StandardRow({ standard, isVisible, onEdit, onDelete, onDuplicate, onToggleVisibility, customizedCounts }) {
  const {
    showDeleteModal, showDuplicateModal, downloadError,
    openDelete, closeDelete, confirmDelete,
    openDuplicate, closeDuplicate, confirmDuplicate,
    handleDownload,
  } = useStandardRowModals({ standard, onDelete, onDuplicate });
  const principleCount = standard.principleCount ?? standard.principles?.length ?? 0;
  const requirementCount = standard.requirementCount ?? (standard.principles || []).reduce((sum, p) => sum + (p.requirements?.length ?? 0), 0);
  const isDeletable = isDeletableStandard(standard.type);
  const baseLabel = BASE_LABELS[standard.type] || standard.type;

  return (
    <>
      <StandardRowMain
        standard={standard} isVisible={isVisible} onToggleVisibility={onToggleVisibility} baseLabel={baseLabel}
        customizedCounts={customizedCounts} principleCount={principleCount} requirementCount={requirementCount}
        isDeletable={isDeletable} onEdit={onEdit} openDuplicate={openDuplicate} handleDownload={handleDownload} openDelete={openDelete}
      />
      {downloadError && (
        <div role="alert" className="standards-row-error">
          {t('standards.downloadError', { message: downloadError })}
        </div>
      )}
      {showDeleteModal && (
        <ConfirmDeleteModal
          standardName={standard.name}
          principleCount={principleCount}
          requirementCount={requirementCount}
          onConfirm={confirmDelete}
          onCancel={closeDelete}
        />
      )}
      {showDuplicateModal && (
        <DuplicateModal
          standardId={standard.id}
          onConfirm={confirmDuplicate}
          onCancel={closeDuplicate}
        />
      )}
    </>
  );
}

export default function StandardsTable({ grouped, actions, customizedCounts }) {
  const { onEdit, onDelete, onDuplicate, isVisible, onToggleVisibility } = actions;
  const all = useMemo(
    () => [...(grouped.builtin || []), ...(grouped.quodeq || []), ...(grouped.community || []), ...(grouped.custom || [])],
    [grouped],
  );

  if (all.length === 0) {
    return (
      <div className="standards-empty">
        <p>{t('standards.noStandardsFound')}</p>
      </div>
    );
  }

  return (
    <div className="standards-table" role="table">
      <div className="standards-table-head" role="row">
        <div className="standards-cell standards-cell--name">{t('standards.colName')}</div>
        <div className="standards-cell standards-cell--base">{t('standards.colBase')}</div>
        <div className="standards-cell standards-cell--num">{t('standards.colPrinciples')}</div>
        <div className="standards-cell standards-cell--num">{t('standards.colRequirements')}</div>
        <div className="standards-cell standards-cell--enabled">{t('standards.colEnabled')}</div>
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
            customizedCounts={customizedCounts}
          />
        ))}
      </div>
    </div>
  );
}
