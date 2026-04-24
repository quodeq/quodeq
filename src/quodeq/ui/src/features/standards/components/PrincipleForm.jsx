import { useRef, useEffect } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

export default function PrincipleForm({ principle, principleIndex, onUpdateField, editable }) {
  const nameRef = useRef(null);

  useEffect(() => {
    if (!principle.name && nameRef.current) nameRef.current.focus();
  }, [principleIndex]);

  return (
    <div className="principle-form">
      <SectionLabel marker="▶">Principle</SectionLabel>

      <div className="form-group">
        <label htmlFor={`principle-name-${principleIndex}`}>Name</label>
        <input
          ref={nameRef}
          id={`principle-name-${principleIndex}`}
          className="form-input"
          value={principle.name || ''}
          onChange={(e) => onUpdateField(['principles', principleIndex, 'name'], e.target.value)}
          disabled={!editable}
          placeholder="e.g. Dependency Rule"
        />
      </div>

      <div className="form-group">
        <label htmlFor={`principle-desc-${principleIndex}`}>Description</label>
        <textarea
          id={`principle-desc-${principleIndex}`}
          className="form-textarea"
          value={principle.description || ''}
          onChange={(e) => onUpdateField(['principles', principleIndex, 'description'], e.target.value)}
          disabled={!editable}
          placeholder="Describe this principle..."
          rows={4}
        />
      </div>

      <div className="principle-form-meta">
        <span className="principle-form-req-count">
          {principle.requirements?.length ?? 0} requirement{(principle.requirements?.length ?? 0) === 1 ? '' : 's'}
        </span>
      </div>
    </div>
  );
}
