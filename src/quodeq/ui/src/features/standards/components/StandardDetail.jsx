import PrincipleForm from './PrincipleForm.jsx';
import RequirementForm from './RequirementForm.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

function slugify(text) {
  return text.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function EmptyState() {
  return (
    <p className="detail-empty-state">
      Add your first principle from the tree on the left, then define requirements for each one.
    </p>
  );
}

function NameField({ standard, editable, isNew, onUpdateField }) {
  const handleNameChange = (e) => {
    const name = e.target.value;
    onUpdateField(['name'], name);
    if (isNew || !standard.id || standard.id === slugify(standard.name || '')) {
      onUpdateField(['id'], slugify(name));
    }
  };
  return (
    <div className="form-group">
      <label htmlFor="std-name">Name</label>
      <input id="std-name" className="form-input" value={standard.name || ''} onChange={handleNameChange} disabled={!editable} placeholder="e.g. Clean Architecture" autoFocus={isNew} />
    </div>
  );
}

function DescriptionField({ standard, editable, onUpdateField }) {
  return (
    <div className="form-group">
      <label htmlFor="std-description">Description</label>
      <textarea id="std-description" className="form-textarea" value={standard.description || ''} onChange={(e) => onUpdateField(['description'], e.target.value)} disabled={!editable} placeholder="Describe this standard..." rows={4} />
    </div>
  );
}

function SourceField({ standard, editable, onUpdateField }) {
  return (
    <div className="form-group">
      <label htmlFor="std-source">Source</label>
      <input id="std-source" className="form-input" value={standard.source || ''} onChange={(e) => onUpdateField(['source'], e.target.value)} disabled={!editable} placeholder="e.g. https://example.com/standard" />
    </div>
  );
}

function RootDetail({ standard, onUpdateField, editable, isNew }) {
  return (
    <div className="standard-root-detail">
      <SectionLabel marker="▶">Standard</SectionLabel>
      <NameField standard={standard} editable={editable} isNew={isNew} onUpdateField={onUpdateField} />
      <input type="hidden" value={standard.id || ''} />
      <DescriptionField standard={standard} editable={editable} onUpdateField={onUpdateField} />
      <SourceField standard={standard} editable={editable} onUpdateField={onUpdateField} />
      {standard.managed && <p className="detail-managed-notice">Managed standard. Fields are read-only to preserve upstream compatibility.</p>}
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
