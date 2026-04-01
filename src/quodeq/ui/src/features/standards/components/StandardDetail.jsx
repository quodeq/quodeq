import PrincipleForm from './PrincipleForm.jsx';
import RequirementForm from './RequirementForm.jsx';

function slugify(text) {
  return text.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function EmptyState() {
  return (
    <div className="detail-empty-state">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="16" />
        <line x1="8" y1="12" x2="16" y2="12" />
      </svg>
      <h4>Start building your evaluator</h4>
      <p>Add your first principle from the tree panel, then define requirements for each one.</p>
    </div>
  );
}

function RootDetail({ standard, onUpdateField, editable, isNew }) {
  const handleNameChange = (e) => {
    const name = e.target.value;
    onUpdateField(['name'], name);
    if (isNew || !standard.id || standard.id === slugify(standard.name || '')) {
      onUpdateField(['id'], slugify(name));
    }
  };

  return (
    <div className="standard-root-detail">
      <h3 className="detail-form-title">Standard Details</h3>

      <div className="form-group">
        <label htmlFor="std-name">Name</label>
        <input
          id="std-name"
          className="form-input"
          value={standard.name || ''}
          onChange={handleNameChange}
          disabled={!editable}
          placeholder="e.g. Clean Architecture"
          autoFocus={isNew}
        />
      </div>

      <input type="hidden" value={standard.id || ''} />

      <div className="form-group">
        <label htmlFor="std-description">Description</label>
        <textarea
          id="std-description"
          className="form-textarea"
          value={standard.description || ''}
          onChange={(e) => onUpdateField(['description'], e.target.value)}
          disabled={!editable}
          placeholder="Describe this standard..."
          rows={4}
        />
      </div>

      <div className="form-group">
        <label htmlFor="std-source">Source</label>
        <input
          id="std-source"
          className="form-input"
          value={standard.source || ''}
          onChange={(e) => onUpdateField(['source'], e.target.value)}
          disabled={!editable}
          placeholder="e.g. https://example.com/standard"
        />
      </div>

      {standard.managed && (
        <p className="detail-managed-notice">
          This is a managed standard. Fields are read-only to preserve upstream compatibility.
        </p>
      )}

      {editable && (!standard.principles || standard.principles.length === 0) && <EmptyState />}
    </div>
  );
}

export default function StandardDetail({ standard, selectedNode, onUpdateField, editable, isNew }) {
  if (!selectedNode || !standard) return null;

  if (selectedNode.type === 'root') {
    return <RootDetail standard={standard} onUpdateField={onUpdateField} editable={editable} isNew={isNew} />;
  }

  if (selectedNode.type === 'principle') {
    const principle = standard.principles[selectedNode.index];
    if (!principle) return null;
    return (
      <PrincipleForm
        principle={principle}
        principleIndex={selectedNode.index}
        onUpdateField={onUpdateField}
        editable={editable}
      />
    );
  }

  if (selectedNode.type === 'requirement') {
    const principle = standard.principles[selectedNode.principleIndex];
    if (!principle) return null;
    const requirement = principle.requirements[selectedNode.reqIndex];
    if (!requirement) return null;
    return (
      <RequirementForm
        requirement={requirement}
        principleIndex={selectedNode.principleIndex}
        reqIndex={selectedNode.reqIndex}
        onUpdateField={onUpdateField}
        editable={editable}
      />
    );
  }

  return null;
}
