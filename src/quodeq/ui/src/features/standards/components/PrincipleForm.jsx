import { useRef, useEffect } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';

export default function PrincipleForm({ principle, principleIndex, onUpdateField, editable }) {
  const nameRef = useRef(null);

  useEffect(() => {
    if (!principle.name && nameRef.current) nameRef.current.focus();
  }, [principleIndex]);

  return (
    <div className="principle-form">
      <SectionLabel marker="▶">{t('standards.principleLabel')}</SectionLabel>

      <div className="form-group">
        <label htmlFor={`principle-name-${principleIndex}`}>{t('standards.colName')}</label>
        <input
          ref={nameRef}
          id={`principle-name-${principleIndex}`}
          className="form-input"
          value={principle.name || ''}
          onChange={(e) => onUpdateField(['principles', principleIndex, 'name'], e.target.value)}
          disabled={!editable}
          placeholder={t('standards.principleNamePlaceholder')}
        />
      </div>

      <div className="form-group">
        <label htmlFor={`principle-desc-${principleIndex}`}>{t('standards.descriptionLabel')}</label>
        <textarea
          id={`principle-desc-${principleIndex}`}
          className="form-textarea"
          value={principle.description || ''}
          onChange={(e) => onUpdateField(['principles', principleIndex, 'description'], e.target.value)}
          disabled={!editable}
          placeholder={t('standards.describePrinciplePlaceholder')}
          rows={4}
        />
      </div>

      <div className="principle-form-meta">
        <span className="principle-form-req-count">
          {(principle.requirements?.length ?? 0) === 1
            ? t('standards.requirementsCountOne', { count: principle.requirements?.length ?? 0 })
            : t('standards.requirementsCountMany', { count: principle.requirements?.length ?? 0 })}
        </span>
      </div>
    </div>
  );
}
